"""
Quick Setup Script - Fix Alembic and Initialize Database
Run this from the backend directory
"""
import os
import sys
import subprocess
from pathlib import Path
import shutil

def run_command(command, description):
    """Run a shell command and handle errors"""
    print(f"\n{'='*60}")
    print(f"🔧 {description}")
    print(f"{'='*60}")
    print(f"Running: {command}")
    
    result = subprocess.run(command, shell=True, capture_output=True, text=True)
    
    if result.stdout:
        print(result.stdout)
    if result.stderr:
        print(result.stderr)
    
    if result.returncode != 0:
        print(f"❌ Failed with return code {result.returncode}")
        return False
    else:
        print(f"✅ Success!")
        return True

def main():
    print("""
╔═══════════════════════════════════════════════════════════╗
║   Quizzie Backend - Database Setup                        ║
║   Fixing Alembic Configuration                            ║
╚═══════════════════════════════════════════════════════════╝
    """)
    
    # Check if we're in the backend directory
    if not Path('app').exists():
        print("❌ Error: Please run this script from the backend directory")
        print("   cd C:\\Projects\\Quizzie\\backend")
        sys.exit(1)
    
    print("✅ Found backend directory")
    
    # Step 1: Check if alembic directory exists
    alembic_dir = Path('alembic')
    if not alembic_dir.exists():
        print("\n📁 Creating alembic directory structure...")
        alembic_dir.mkdir(exist_ok=True)
        (alembic_dir / 'versions').mkdir(exist_ok=True)
        print("✅ Alembic directory created")
    else:
        print("✅ Alembic directory exists")
    
    # Step 2: Copy alembic.ini if needed
    if not Path('alembic.ini').exists():
        print("\n⚠️  alembic.ini not found!")
        print("📝 Please create alembic.ini with the following content:")
        print("""
[alembic]
script_location = alembic
prepend_sys_path = .
sqlalchemy.url = postgresql://postgres:password@localhost:5432/quizzie_db

[loggers]
keys = root,sqlalchemy,alembic

[handlers]
keys = console

[formatters]
keys = generic

[logger_root]
level = WARN
handlers = console
qualname =

[logger_sqlalchemy]
level = WARN
handlers =
qualname = sqlalchemy.engine

[logger_alembic]
level = INFO
handlers =
qualname = alembic

[handler_console]
class = StreamHandler
args = (sys.stderr,)
level = NOTSET
formatter = generic

[formatter_generic]
format = %(levelname)-5.5s [%(name)s] %(message)s
datefmt = %H:%M:%S
        """)
        
        # Create a basic alembic.ini
        with open('alembic.ini', 'w') as f:
            f.write("""[alembic]
script_location = alembic
prepend_sys_path = .
sqlalchemy.url = postgresql://postgres:password@localhost:5432/quizzie_db

[loggers]
keys = root,sqlalchemy,alembic

[handlers]
keys = console

[formatters]
keys = generic

[logger_root]
level = WARN
handlers = console
qualname =

[logger_sqlalchemy]
level = WARN
handlers =
qualname = sqlalchemy.engine

[logger_alembic]
level = INFO
handlers =
qualname = alembic

[handler_console]
class = StreamHandler
args = (sys.stderr,)
level = NOTSET
formatter = generic

[formatter_generic]
format = %(levelname)-5.5s [%(name)s] %(message)s
datefmt = %H:%M:%S
""")
        print("✅ Created alembic.ini")
    else:
        print("✅ alembic.ini exists")
    
    # Step 3: Check/create env.py
    env_py = alembic_dir / 'env.py'
    if not env_py.exists():
        print("\n📝 Creating alembic/env.py...")
        with open(env_py, 'w') as f:
            f.write("""from logging.config import fileConfig
from sqlalchemy import engine_from_config, pool
from alembic import context
import sys
import os

sys.path.insert(0, os.path.dirname(os.path.dirname(__file__)))

from app.core.database import Base
from app.core.config import settings

# Import all models
from app.models.user import User
from app.models.exam import Exam
from app.models.question import Question, Option
from app.models.attempt import ExamAttempt, Response
from app.models.cheat_log import CheatLog

config = context.config
config.set_main_option('sqlalchemy.url', settings.DATABASE_URL)

if config.config_file_name is not None:
    fileConfig(config.config_file_name)

target_metadata = Base.metadata

def run_migrations_offline():
    url = config.get_main_option("sqlalchemy.url")
    context.configure(
        url=url,
        target_metadata=target_metadata,
        literal_binds=True,
        dialect_opts={"paramstyle": "named"},
    )
    with context.begin_transaction():
        context.run_migrations()

def run_migrations_online():
    connectable = engine_from_config(
        config.get_section(config.config_ini_section),
        prefix="sqlalchemy.",
        poolclass=pool.NullPool,
    )
    with connectable.connect() as connection:
        context.configure(connection=connection, target_metadata=target_metadata)
        with context.begin_transaction():
            context.run_migrations()

if context.is_offline_mode():
    run_migrations_offline()
else:
    run_migrations_online()
""")
        print("✅ Created alembic/env.py")
    else:
        print("✅ alembic/env.py exists")
    
    # Step 4: Check if script.py.mako exists
    mako = alembic_dir / 'script.py.mako'
    if not mako.exists():
        print("\n📝 Creating alembic/script.py.mako...")
        with open(mako, 'w') as f:
            f.write("""\"\"\"${message}

Revision ID: ${up_revision}
Revises: ${down_revision | comma,n}
Create Date: ${create_date}

\"\"\"
from alembic import op
import sqlalchemy as sa
${imports if imports else ""}

# revision identifiers, used by Alembic.
revision = ${repr(up_revision)}
down_revision = ${repr(down_revision)}
branch_labels = ${repr(branch_labels)}
depends_on = ${repr(depends_on)}


def upgrade():
    ${upgrades if upgrades else "pass"}


def downgrade():
    ${downgrades if downgrades else "pass"}
""")
        print("✅ Created alembic/script.py.mako")
    else:
        print("✅ alembic/script.py.mako exists")
    
    print("\n" + "="*60)
    print("🎉 Alembic setup complete!")
    print("="*60)
    
    print("""
📋 Next Steps:

1. Update your .env file with database credentials:
   DATABASE_URL=postgresql://postgres:YOUR_PASSWORD@localhost:5432/quizzie_db

2. Ensure PostgreSQL is running

3. Create the database (if not exists):
   psql -U postgres
   CREATE DATABASE quizzie_db;
   \\q

4. Create the migration:
   alembic revision --autogenerate -m "Add proctoring settings"

5. Review the migration file in alembic/versions/

6. Apply the migration:
   alembic upgrade head

7. Or use the pre-made migration file (add_proctoring_migration.py):
   - Copy it to alembic/versions/ with a proper name
   - Then run: alembic upgrade head
    """)

if __name__ == '__main__':
    try:
        main()
    except KeyboardInterrupt:
        print("\n\n⚠️  Setup interrupted")
        sys.exit(1)
    except Exception as e:
        print(f"\n❌ Error: {e}")
        import traceback
        traceback.print_exc()
        sys.exit(1)
