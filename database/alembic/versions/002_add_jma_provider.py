"""add jma provider

Revision ID: 002
Revises: 001
Create Date: 2026-08-08

"""

from typing import Sequence, Union

from alembic import op

revision: str = "002"
down_revision: Union[str, None] = "001"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.execute(
        """
        INSERT INTO providers (id, name, country, api_type, update_frequency, attribution)
        VALUES
        (
          'JMA',
          'Japan Meteorological Agency AMeDAS',
          'JP',
          'JSON',
          'Hourly',
          'Japan Meteorological Agency (JMA) AMeDAS — https://www.jma.go.jp/jma/kishou/info/coment.html'
        )
        ON CONFLICT (id) DO NOTHING
        """
    )


def downgrade() -> None:
    op.execute("DELETE FROM providers WHERE id = 'JMA'")
