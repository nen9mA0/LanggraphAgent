from dotenv import load_dotenv
from pathlib import Path
import os

def get_absolute_db_path(keep_url: bool = True) -> str:

    root_dir = Path(__file__).resolve().parents[2]
    load_dotenv(root_dir / ".env")

    raw_url = os.getenv("DATABASE_URL", "sqlite:///storage/dev.db")

    if not raw_url.startswith("sqlite:///"):
        raise ValueError(
            f"Unsupported DATABASE_URL: {raw_url}. Only sqlite URLs like "
            "'sqlite:///storage/dev.db' are currently supported."
        )

    relative_path = raw_url.replace("sqlite:///", "", 1)
    db_file = root_dir / relative_path


    db_path =  f"sqlite:///{db_file.resolve()}" if keep_url else db_file.resolve()

    return db_path
