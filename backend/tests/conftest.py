import os


# Izolirane nastavitve testnega procesa; povezave v PostgreSQL se nadomestijo.
os.environ["DATABASE_URL"] = "postgresql+psycopg://test:test@localhost/test"
os.environ["JWT_SECRET"] = "test-only-signing-key-with-at-least-32-bytes"
