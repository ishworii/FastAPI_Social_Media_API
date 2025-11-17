from fastapi import APIRouter, Depends, HTTPException, Query, status
from fastapi_limiter.depends import RateLimiter
from sqlalchemy import text
from sqlalchemy.orm import Session

from app.api.deps import PostCache, get_current_user, get_db
from app.crud import like, post
from app.models.like import Like
from app.models.post import Post, Subscription, Tag
from app.models.user import User, UserRole
from app.schemas.like import Action
from app.schemas.post import PostCreate, PostRead

router = APIRouter()


@router.get(
    "/",
    response_model=list[PostRead],
    status_code=status.HTTP_200_OK,
    dependencies=[Depends(RateLimiter(times=20, seconds=5))],
)
def get_all_posts(
    db: Session = Depends(get_db),
    author_id: int = Query(None, description="Filter by author id"),
    min_likes: int = Query(None, description="Filter by minimum number of likes"),
    title: str = Query(None, description="Filter by title"),
    tags : str = Query(None,description="Filter by tags separated by comma"),
):
    query = db.query(Post)
    if author_id:
        query = query.filter(Post.author_id == author_id)
    if min_likes:
        query = query.filter(Post.like_count >= min_likes)
    if title:
        query = query.filter(Post.title.ilike(f"%{title.strip()}%"))
    if tags:
        all_tags = tags.split(",")
        query = query.filter(Post.tags.any(Tag.name.in_(all_tags)))
    posts = query.all()
    return posts


@router.post(
    "/",
    response_model=PostRead,
    status_code=status.HTTP_201_CREATED,
    dependencies=[Depends(RateLimiter(times=20, seconds=5))],
)
def create_post(
    post_create: PostCreate,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    post_data = post_create.model_dump(exclude={"tags"})
    new_post = Post(**post_data, author_id=current_user.id)
    if post_create.tags:
        for tag_data in post_create.tags:
            tag = (
                db.query(Tag).filter(Tag.name == tag_data.name.lower().strip()).first()
            )
            if not tag:
                tag = Tag(name=tag_data.name.lower().strip())
                db.add(tag)
            new_post.tags.append(tag)
    db.add(new_post)
    db.commit()
    db.refresh(new_post)
    return new_post

# LIKE "dfsd"
@router.get("/search", dependencies=[Depends(RateLimiter(times=20, seconds=5))])
async def search_posts(query: str, db: Session = Depends(get_db)):
    sql_query = """
        SELECT * 
        FROM post 
        WHERE search_vector @@ plainto_tsquery('english', :query)
        ORDER BY ts_rank_cd(search_vector, plainto_tsquery('english', :query)) DESC;
    """
    result = db.execute(text(sql_query), {"query": query}).fetchall()

    posts = [
        {
            "id": row[0],
            "title": row[1],
            "content": row[2],
            "created_at": row[3].isoformat(),
            "author_id": row[4],
            "like_count": row[5],
            "dislike_count": row[6],
        }
        for row in result
    ]

    return posts


@router.get(
    "/{post_id}",
    response_model=PostRead,
    status_code=status.HTTP_200_OK,
    dependencies=[Depends(RateLimiter(times=20, seconds=5))],
)
async def get_post(cache: PostCache, post_id: int, db: Session = Depends(get_db)):
    cache_key = str(post_id)
    if cached_data := await cache.get(cache_key):
        return PostRead(**cached_data)
    post = db.query(Post).filter(Post.id == post_id).first()
    if not post:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Post with id:{post_id} not found",
        )
    post_dict = {
        "id": post.id,
        "title": post.title,
        "content": post.content,
        "created_at": post.created_at,
        "author_id": post.author_id,
        "like_count": post.like_count,
        "dislike_count": post.dislike_count,
        "tags": [{"id": tag.id, "name": tag.name} for tag in post.tags]
    }
    await cache.set(cache_key, post_dict)
    return post


@router.put("/{post_id}", response_model=PostRead, status_code=status.HTTP_201_CREATED)
async def update_post(
    cache: PostCache,
    post_id: int,
    post_read: PostCreate,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    db_post = db.query(Post).filter(Post.id == post_id).first()
    if not db_post:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND, detail="Post not found"
        )
    if db_post.author_id != current_user.id and current_user.role != UserRole.admin:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN, detail="Not enough permissions"
        )
    db_post.title = post_read.title
    db_post.content = post_read.content
    db_post.author_id = current_user.id
    #check if the tags are already in db or not
    updated_tags = []
    for each_tag in post_read.tags:
        tag = (
                db.query(Tag).filter(Tag.name == each_tag.name.lower().strip()).first()
            )
        if not tag:
            tag = Tag(name=each_tag.name.lower().strip())
            db.add(tag)
        updated_tags.append(tag)
    db_post.tags = updated_tags
    db.commit()
    db.refresh(db_post)
    await cache.delete(str(post_id))
    return db_post


@router.delete("/{post_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_post(
    cache: PostCache,
    post_id: int,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    db_post = db.query(Post).filter(Post.id == post_id).first()
    if not db_post:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND, detail="Post not found"
        )
    if db_post.author_id != current_user.id and current_user.role != UserRole.admin:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN, detail="Not enough permissions"
        )
    await cache.delete(str(db_post.id))
    db.delete(db_post)
    db.commit()
    return {"detail": "Post deleted"}


# like/dislike/subscribe/unsubscribe a post
@router.post("/{id}/{action}", status_code=status.HTTP_201_CREATED)
async def like_dislike_post(
    cache: PostCache,
    id: int,
    action: Action,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    cache_key = str(id)
    get_a_post = post.get_post(db, id)
    if not get_a_post:
        raise HTTPException(status_code=404, detail="detail not found")
    if action == Action.like:
        like.like_post(db, current_user, get_a_post)
    elif action == Action.dislike:
        like.dislike_post(db, current_user, get_a_post)
    elif action == Action.subscribe:
        if current_user.id == get_a_post.author_id:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="Can not subscribe your own post",
            )
        subscription = (
            db.query(Subscription)
            .filter_by(post_id=get_a_post.id, user_id=current_user.id)
            .first()
        )
        if subscription:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST, detail="Already subscribed"
            )
        new_subscription = Subscription(user_id=current_user.id, post_id=get_a_post.id)
        db.add(new_subscription)
        db.commit()
        db.refresh(new_subscription)
        await cache.delete(cache_key)
        return {
            "message": "subscribed successfully",
            "user_id": current_user.id,
            "post_id": get_a_post.id,
        }
    elif action == Action.unsubscribe:
        if current_user.id == get_a_post.author_id:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="Can not unsubscribe your own post",
            )
        subscription = (
            db.query(Subscription)
            .filter_by(post_id=get_a_post.id, user_id=current_user.id)
            .first()
        )
        if not subscription:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST, detail="Not subscribed"
            )
        db.delete(subscription)
        db.commit()
        await cache.delete(cache_key)
        return {
            "message": "Unsubscribed successfully",
            "post_id": get_a_post.id,
            "user_id": current_user.id,
        }

    like_record = (
        db.query(Like)
        .filter(Like.user_id == current_user.id, Like.post_id == get_a_post.id)
        .first()
    )
    is_like = like_record.is_like if like_record else False
    await cache.delete(cache_key)
    return {"post_id": get_a_post.id, "user_id": current_user.id, "is_like": is_like}
