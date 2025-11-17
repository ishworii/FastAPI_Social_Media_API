
import asyncio
import random
from faker import Faker
from sqlalchemy.orm import sessionmaker
from app.db.session import engine
from app.db.base import Base
from app.models.user import User, UserRole
from app.models.post import Post, Tag, Subscription
from app.models.comment import Comment
from app.models.like import Like
from app.utils.hashing import hash_password

fake = Faker()

SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)

async def populate_db():
    db = SessionLocal()

    # Create tables
    Base.metadata.create_all(bind=engine)

    # Create users
    users = []
    for _ in range(30):
        user = User(
            username=fake.user_name(),
            email=fake.email(),
            full_name=fake.name(),
            hashed_password=hash_password("password"),
            role=random.choice(list(UserRole)),
        )
        users.append(user)
    db.add_all(users)
    db.commit()

    # Create tags
    tags = []
    for _ in range(20):
        tag = Tag(name=fake.word())
        tags.append(tag)
    db.add_all(tags)
    db.commit()

    # Create posts
    posts = []
    for _ in range(30):
        post = Post(
            title=fake.sentence(),
            content=fake.text(),
            author=random.choice(users),
            tags=random.sample(tags, k=random.randint(1, 5)),
        )
        posts.append(post)
    db.add_all(posts)
    db.commit()

    # Create comments
    comments = []
    for _ in range(50):
        comment = Comment(
            content=fake.text(),
            post=random.choice(posts),
            user=random.choice(users),
        )
        comments.append(comment)
    db.add_all(comments)
    db.commit()

    # Create likes
    likes = []
    for post in posts:
        for user in random.sample(users, k=random.randint(0, len(users))):
            like = Like(
                post=post,
                user=user,
                is_like=random.choice([True, False]),
            )
            likes.append(like)
    db.add_all(likes)
    db.commit()

    # Create subscriptions
    subscriptions = []
    for post in posts:
        for user in random.sample(users, k=random.randint(0, 5)):
            if not any(s.user_id == user.id and s.post_id == post.id for s in subscriptions):
                subscription = Subscription(
                    post=post,
                    user=user,
                )
                subscriptions.append(subscription)
    db.add_all(subscriptions)
    db.commit()

    # Create user follows
    for user in users:
        following = random.sample(users, k=random.randint(0, 10))
        for follow in following:
            if user.id != follow.id:
                user.following.append(follow)
    db.commit()

    db.close()

if __name__ == "__main__":
    asyncio.run(populate_db())
