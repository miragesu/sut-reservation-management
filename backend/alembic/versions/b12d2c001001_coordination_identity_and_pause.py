"""Stable usage/queue identities and resumable offer deadlines."""
from alembic import op
import sqlalchemy as sa

revision = 'b12d2c001001'
down_revision = 'fd0b3a205c15'
branch_labels = None
depends_on = None


def upgrade():
    # Backfill existing Day 1 records without changing their ownership/state.
    op.add_column('current_usages', sa.Column('usage_key', sa.String(64), nullable=True))
    op.execute('UPDATE current_usages SET usage_key = lower(hex(randomblob(16)))')
    with op.batch_alter_table('current_usages') as batch:
        batch.alter_column('usage_key', existing_type=sa.String(64), nullable=False)
        batch.create_unique_constraint('uq_current_usages_usage_key', ['usage_key'])
    op.add_column('queue_entries', sa.Column('entry_key', sa.String(64), nullable=True))
    op.execute('UPDATE queue_entries SET entry_key = lower(hex(randomblob(16)))')
    with op.batch_alter_table('queue_entries') as batch:
        batch.alter_column('entry_key', existing_type=sa.String(64), nullable=False)
        batch.create_unique_constraint('uq_queue_entries_entry_key', ['entry_key'])
        batch.add_column(sa.Column('offer_generation', sa.Integer(), nullable=False, server_default='0'))
        batch.add_column(sa.Column('paused_at', sa.DateTime(), nullable=True))
        batch.add_column(sa.Column('remaining_microseconds', sa.Integer(), nullable=True))
    with op.batch_alter_table('usage_histories') as batch:
        batch.add_column(sa.Column('purpose', sa.Text(), nullable=True))
        batch.add_column(sa.Column('released_by_user_id', sa.Integer(), nullable=True))
        batch.add_column(sa.Column('release_note', sa.Text(), nullable=True))
        batch.create_foreign_key('fk_usage_histories_released_by_user_id_users', 'users', ['released_by_user_id'], ['id'])


def downgrade():
    with op.batch_alter_table('usage_histories') as batch:
        batch.drop_constraint('fk_usage_histories_released_by_user_id_users', type_='foreignkey')
        for column in ('release_note', 'released_by_user_id', 'purpose'):
            batch.drop_column(column)
    with op.batch_alter_table('queue_entries') as batch:
        batch.drop_constraint('uq_queue_entries_entry_key', type_='unique')
        for column in ('remaining_microseconds', 'paused_at', 'offer_generation', 'entry_key'):
            batch.drop_column(column)
    with op.batch_alter_table('current_usages') as batch:
        batch.drop_constraint('uq_current_usages_usage_key', type_='unique')
        batch.drop_column('usage_key')
