from kokoro.common.database.base import Base
from kokoro.common.database import engine

def init_db():
    Base.metadata.create_all(bind=engine)
    print("Database initialized successfully")

if __name__ == "__main__":
    init_db()

