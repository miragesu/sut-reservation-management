"""Availability-based start window; manual attendance no longer exempts expiry."""
from alembic import op
import sqlalchemy as sa

revision = 'c2026101601'
down_revision = 'b12d2c001001'
branch_labels = None
depends_on = None


def upgrade():
    op.add_column('reservations', sa.Column('ready_at', sa.DateTime(), nullable=True))
    op.add_column('reservations', sa.Column('start_deadline', sa.DateTime(), nullable=True))
    op.add_column('reservations', sa.Column('start_remaining_microseconds', sa.Integer(), nullable=True))
    # Retain attendance timestamps for history, but they no longer grant indefinite protection.
    op.execute("UPDATE reservations SET status='confirmed' WHERE status='waiting_for_release'")


def downgrade():
    raise RuntimeError('Restore a compatible backup; automatic state-policy downgrade is unsupported')
