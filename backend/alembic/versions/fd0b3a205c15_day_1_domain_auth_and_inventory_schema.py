"""Day 1 domain auth and inventory schema"""
from alembic import op
import sqlalchemy as sa

revision = 'fd0b3a205c15'
down_revision = None
branch_labels = None
depends_on = None


def upgrade():
    op.create_table('labs',
    sa.Column('id', sa.Integer(), nullable=False),
    sa.Column('name', sa.String(length=120), nullable=False),
    sa.Column('location', sa.String(length=200), nullable=False),
    sa.Column('description', sa.Text(), nullable=False),
    sa.Column('created_at', sa.DateTime(), nullable=False),
    sa.PrimaryKeyConstraint('id', name=op.f('pk_labs')),
    sa.UniqueConstraint('name', name=op.f('uq_labs_name'))
    )
    op.create_table('users',
    sa.Column('id', sa.Integer(), nullable=False),
    sa.Column('username', sa.String(length=80), nullable=False),
    sa.Column('display_name', sa.String(length=120), nullable=False),
    sa.Column('team', sa.String(length=80), nullable=False),
    sa.Column('email', sa.String(length=254), nullable=False),
    sa.Column('password_hash', sa.Text(), nullable=False),
    sa.Column('role', sa.String(length=20), nullable=False),
    sa.Column('is_active', sa.Boolean(), nullable=False),
    sa.Column('must_change_password', sa.Boolean(), nullable=False),
    sa.Column('password_changed_at', sa.DateTime(), nullable=True),
    sa.Column('deactivated_at', sa.DateTime(), nullable=True),
    sa.Column('deactivated_by_user_id', sa.Integer(), nullable=True),
    sa.Column('deactivation_reason', sa.Text(), nullable=True),
    sa.Column('created_at', sa.DateTime(), nullable=False),
    sa.CheckConstraint("role IN ('user','lab_admin','super_admin')", name=op.f('ck_users_role')),
    sa.ForeignKeyConstraint(['deactivated_by_user_id'], ['users.id'], name=op.f('fk_users_deactivated_by_user_id_users')),
    sa.PrimaryKeyConstraint('id', name=op.f('pk_users')),
    sa.UniqueConstraint('email', name=op.f('uq_users_email')),
    sa.UniqueConstraint('username', name=op.f('uq_users_username'))
    )
    op.create_table('login_sessions',
    sa.Column('id', sa.String(length=64), nullable=False),
    sa.Column('user_id', sa.Integer(), nullable=False),
    sa.Column('expires_at', sa.DateTime(), nullable=False),
    sa.Column('created_at', sa.DateTime(), nullable=False),
    sa.ForeignKeyConstraint(['user_id'], ['users.id'], name=op.f('fk_login_sessions_user_id_users')),
    sa.PrimaryKeyConstraint('id', name=op.f('pk_login_sessions'))
    )
    with op.batch_alter_table('login_sessions', schema=None) as batch_op:
        batch_op.create_index(batch_op.f('ix_login_sessions_expires_at'), ['expires_at'], unique=False)
        batch_op.create_index(batch_op.f('ix_login_sessions_user_id'), ['user_id'], unique=False)

    op.create_table('suts',
    sa.Column('id', sa.Integer(), nullable=False),
    sa.Column('lab_id', sa.Integer(), nullable=False),
    sa.Column('name', sa.String(length=120), nullable=False),
    sa.Column('normalized_name', sa.String(length=240), nullable=False),
    sa.Column('platform', sa.String(length=100), nullable=False),
    sa.Column('owner_team', sa.String(length=80), nullable=False),
    sa.Column('description', sa.Text(), nullable=False),
    sa.Column('bmc_ip', sa.String(length=45), nullable=True),
    sa.Column('host_ip', sa.String(length=45), nullable=True),
    sa.Column('updated_at', sa.DateTime(), nullable=False),
    sa.Column('is_archived', sa.Boolean(), nullable=False),
    sa.Column('archived_at', sa.DateTime(), nullable=True),
    sa.Column('archived_by_user_id', sa.Integer(), nullable=True),
    sa.Column('operational_state', sa.String(length=20), nullable=False),
    sa.Column('operational_reason', sa.Text(), nullable=True),
    sa.Column('operational_updated_at', sa.DateTime(), nullable=True),
    sa.Column('operational_updated_by_user_id', sa.Integer(), nullable=True),
    sa.Column('created_at', sa.DateTime(), nullable=False),
    sa.CheckConstraint("operational_state = 'normal' OR length(trim(operational_reason)) > 0 AND operational_reason IS NOT NULL", name=op.f('ck_suts_operational_reason')),
    sa.CheckConstraint("operational_state IN ('normal','maintenance','out_of_service')", name=op.f('ck_suts_operational_state')),
    sa.ForeignKeyConstraint(['archived_by_user_id'], ['users.id'], name=op.f('fk_suts_archived_by_user_id_users')),
    sa.ForeignKeyConstraint(['lab_id'], ['labs.id'], name=op.f('fk_suts_lab_id_labs')),
    sa.ForeignKeyConstraint(['operational_updated_by_user_id'], ['users.id'], name=op.f('fk_suts_operational_updated_by_user_id_users')),
    sa.PrimaryKeyConstraint('id', name=op.f('pk_suts')),
    sa.UniqueConstraint('lab_id', 'normalized_name', name='uq_suts_lab_normalized_name')
    )
    with op.batch_alter_table('suts', schema=None) as batch_op:
        batch_op.create_index(batch_op.f('ix_suts_is_archived'), ['is_archived'], unique=False)
        batch_op.create_index(batch_op.f('ix_suts_lab_id'), ['lab_id'], unique=False)

    op.create_table('audit_events',
    sa.Column('id', sa.Integer(), nullable=False),
    sa.Column('actor_user_id', sa.Integer(), nullable=True),
    sa.Column('sut_id', sa.Integer(), nullable=True),
    sa.Column('event_type', sa.String(length=80), nullable=False),
    sa.Column('details_json', sa.JSON(), nullable=False),
    sa.Column('created_at', sa.DateTime(), nullable=False),
    sa.ForeignKeyConstraint(['actor_user_id'], ['users.id'], name=op.f('fk_audit_events_actor_user_id_users')),
    sa.ForeignKeyConstraint(['sut_id'], ['suts.id'], name=op.f('fk_audit_events_sut_id_suts')),
    sa.PrimaryKeyConstraint('id', name=op.f('pk_audit_events'))
    )
    with op.batch_alter_table('audit_events', schema=None) as batch_op:
        batch_op.create_index(batch_op.f('ix_audit_events_event_type'), ['event_type'], unique=False)
        batch_op.create_index(batch_op.f('ix_audit_events_sut_id'), ['sut_id'], unique=False)

    op.create_table('notifications',
    sa.Column('id', sa.Integer(), nullable=False),
    sa.Column('user_id', sa.Integer(), nullable=False),
    sa.Column('sut_id', sa.Integer(), nullable=True),
    sa.Column('event_key', sa.String(length=150), nullable=False),
    sa.Column('message', sa.Text(), nullable=False),
    sa.Column('read_at', sa.DateTime(), nullable=True),
    sa.Column('created_at', sa.DateTime(), nullable=False),
    sa.ForeignKeyConstraint(['sut_id'], ['suts.id'], name=op.f('fk_notifications_sut_id_suts')),
    sa.ForeignKeyConstraint(['user_id'], ['users.id'], name=op.f('fk_notifications_user_id_users')),
    sa.PrimaryKeyConstraint('id', name=op.f('pk_notifications')),
    sa.UniqueConstraint('user_id', 'event_key', name=op.f('uq_notifications_user_id'))
    )
    with op.batch_alter_table('notifications', schema=None) as batch_op:
        batch_op.create_index(batch_op.f('ix_notifications_user_id'), ['user_id'], unique=False)

    op.create_table('queue_entries',
    sa.Column('id', sa.Integer(), nullable=False),
    sa.Column('sut_id', sa.Integer(), nullable=False),
    sa.Column('user_id', sa.Integer(), nullable=False),
    sa.Column('requested_duration_minutes', sa.Integer(), nullable=False),
    sa.Column('notified_at', sa.DateTime(), nullable=True),
    sa.Column('offer_expires_at', sa.DateTime(), nullable=True),
    sa.Column('offer_status', sa.String(length=20), nullable=False),
    sa.Column('created_at', sa.DateTime(), nullable=False),
    sa.CheckConstraint("offer_status != 'notified' OR (notified_at IS NOT NULL AND offer_expires_at IS NOT NULL AND offer_expires_at > notified_at)", name=op.f('ck_queue_entries_offer_deadline')),
    sa.CheckConstraint("offer_status IN ('waiting','notified')", name=op.f('ck_queue_entries_offer_status')),
    sa.CheckConstraint('requested_duration_minutes > 0', name=op.f('ck_queue_entries_positive_duration')),
    sa.ForeignKeyConstraint(['sut_id'], ['suts.id'], name=op.f('fk_queue_entries_sut_id_suts')),
    sa.ForeignKeyConstraint(['user_id'], ['users.id'], name=op.f('fk_queue_entries_user_id_users')),
    sa.PrimaryKeyConstraint('id', name=op.f('pk_queue_entries')),
    sa.UniqueConstraint('sut_id', 'user_id', name=op.f('uq_queue_entries_sut_id'))
    )
    with op.batch_alter_table('queue_entries', schema=None) as batch_op:
        batch_op.create_index(batch_op.f('ix_queue_entries_offer_expires_at'), ['offer_expires_at'], unique=False)
        batch_op.create_index(batch_op.f('ix_queue_entries_sut_id'), ['sut_id'], unique=False)
        batch_op.create_index(batch_op.f('ix_queue_entries_user_id'), ['user_id'], unique=False)

    op.create_table('reservations',
    sa.Column('id', sa.Integer(), nullable=False),
    sa.Column('sut_id', sa.Integer(), nullable=False),
    sa.Column('user_id', sa.Integer(), nullable=False),
    sa.Column('start_time', sa.DateTime(), nullable=False),
    sa.Column('end_time', sa.DateTime(), nullable=False),
    sa.Column('purpose', sa.Text(), nullable=False),
    sa.Column('status', sa.String(length=25), nullable=False),
    sa.Column('cancelled_at', sa.DateTime(), nullable=True),
    sa.Column('checked_in_at', sa.DateTime(), nullable=True),
    sa.Column('claimed_at', sa.DateTime(), nullable=True),
    sa.Column('no_show_at', sa.DateTime(), nullable=True),
    sa.Column('created_at', sa.DateTime(), nullable=False),
    sa.CheckConstraint("status IN ('confirmed','waiting_for_release','claimed','cancelled','completed','no_show')", name=op.f('ck_reservations_status')),
    sa.CheckConstraint('end_time > start_time', name=op.f('ck_reservations_positive_interval')),
    sa.ForeignKeyConstraint(['sut_id'], ['suts.id'], name=op.f('fk_reservations_sut_id_suts')),
    sa.ForeignKeyConstraint(['user_id'], ['users.id'], name=op.f('fk_reservations_user_id_users')),
    sa.PrimaryKeyConstraint('id', name=op.f('pk_reservations'))
    )
    with op.batch_alter_table('reservations', schema=None) as batch_op:
        batch_op.create_index(batch_op.f('ix_reservations_end_time'), ['end_time'], unique=False)
        batch_op.create_index(batch_op.f('ix_reservations_start_time'), ['start_time'], unique=False)
        batch_op.create_index(batch_op.f('ix_reservations_status'), ['status'], unique=False)
        batch_op.create_index(batch_op.f('ix_reservations_sut_id'), ['sut_id'], unique=False)
        batch_op.create_index(batch_op.f('ix_reservations_user_id'), ['user_id'], unique=False)

    op.create_table('current_usages',
    sa.Column('id', sa.Integer(), nullable=False),
    sa.Column('sut_id', sa.Integer(), nullable=False),
    sa.Column('user_id', sa.Integer(), nullable=False),
    sa.Column('start_time', sa.DateTime(), nullable=False),
    sa.Column('expected_end_time', sa.DateTime(), nullable=False),
    sa.Column('reservation_id', sa.Integer(), nullable=True),
    sa.Column('purpose', sa.Text(), nullable=True),
    sa.Column('created_at', sa.DateTime(), nullable=False),
    sa.CheckConstraint('expected_end_time > start_time', name=op.f('ck_current_usages_positive_interval')),
    sa.ForeignKeyConstraint(['reservation_id'], ['reservations.id'], name=op.f('fk_current_usages_reservation_id_reservations')),
    sa.ForeignKeyConstraint(['sut_id'], ['suts.id'], name=op.f('fk_current_usages_sut_id_suts')),
    sa.ForeignKeyConstraint(['user_id'], ['users.id'], name=op.f('fk_current_usages_user_id_users')),
    sa.PrimaryKeyConstraint('id', name=op.f('pk_current_usages')),
    sa.UniqueConstraint('sut_id', name=op.f('uq_current_usages_sut_id'))
    )
    with op.batch_alter_table('current_usages', schema=None) as batch_op:
        batch_op.create_index(batch_op.f('ix_current_usages_user_id'), ['user_id'], unique=False)

    op.create_table('usage_histories',
    sa.Column('id', sa.Integer(), nullable=False),
    sa.Column('usage_key', sa.String(length=64), nullable=False),
    sa.Column('sut_id', sa.Integer(), nullable=False),
    sa.Column('user_id', sa.Integer(), nullable=False),
    sa.Column('start_time', sa.DateTime(), nullable=False),
    sa.Column('end_time', sa.DateTime(), nullable=False),
    sa.Column('duration_minutes', sa.Integer(), nullable=False),
    sa.Column('release_reason', sa.String(length=10), nullable=False),
    sa.Column('reservation_id', sa.Integer(), nullable=True),
    sa.Column('created_at', sa.DateTime(), nullable=False),
    sa.CheckConstraint("release_reason IN ('user','admin')", name=op.f('ck_usage_histories_release_reason')),
    sa.CheckConstraint('end_time >= start_time AND duration_minutes >= 0', name=op.f('ck_usage_histories_nonnegative_duration')),
    sa.ForeignKeyConstraint(['reservation_id'], ['reservations.id'], name=op.f('fk_usage_histories_reservation_id_reservations')),
    sa.ForeignKeyConstraint(['sut_id'], ['suts.id'], name=op.f('fk_usage_histories_sut_id_suts')),
    sa.ForeignKeyConstraint(['user_id'], ['users.id'], name=op.f('fk_usage_histories_user_id_users')),
    sa.PrimaryKeyConstraint('id', name=op.f('pk_usage_histories')),
    sa.UniqueConstraint('usage_key', name=op.f('uq_usage_histories_usage_key'))
    )
    with op.batch_alter_table('usage_histories', schema=None) as batch_op:
        batch_op.create_index(batch_op.f('ix_usage_histories_sut_id'), ['sut_id'], unique=False)
        batch_op.create_index(batch_op.f('ix_usage_histories_user_id'), ['user_id'], unique=False)



def downgrade():
    with op.batch_alter_table('usage_histories', schema=None) as batch_op:
        batch_op.drop_index(batch_op.f('ix_usage_histories_user_id'))
        batch_op.drop_index(batch_op.f('ix_usage_histories_sut_id'))

    op.drop_table('usage_histories')
    with op.batch_alter_table('current_usages', schema=None) as batch_op:
        batch_op.drop_index(batch_op.f('ix_current_usages_user_id'))

    op.drop_table('current_usages')
    with op.batch_alter_table('reservations', schema=None) as batch_op:
        batch_op.drop_index(batch_op.f('ix_reservations_user_id'))
        batch_op.drop_index(batch_op.f('ix_reservations_sut_id'))
        batch_op.drop_index(batch_op.f('ix_reservations_status'))
        batch_op.drop_index(batch_op.f('ix_reservations_start_time'))
        batch_op.drop_index(batch_op.f('ix_reservations_end_time'))

    op.drop_table('reservations')
    with op.batch_alter_table('queue_entries', schema=None) as batch_op:
        batch_op.drop_index(batch_op.f('ix_queue_entries_user_id'))
        batch_op.drop_index(batch_op.f('ix_queue_entries_sut_id'))
        batch_op.drop_index(batch_op.f('ix_queue_entries_offer_expires_at'))

    op.drop_table('queue_entries')
    with op.batch_alter_table('notifications', schema=None) as batch_op:
        batch_op.drop_index(batch_op.f('ix_notifications_user_id'))

    op.drop_table('notifications')
    with op.batch_alter_table('audit_events', schema=None) as batch_op:
        batch_op.drop_index(batch_op.f('ix_audit_events_sut_id'))
        batch_op.drop_index(batch_op.f('ix_audit_events_event_type'))

    op.drop_table('audit_events')
    with op.batch_alter_table('suts', schema=None) as batch_op:
        batch_op.drop_index(batch_op.f('ix_suts_lab_id'))
        batch_op.drop_index(batch_op.f('ix_suts_is_archived'))

    op.drop_table('suts')
    with op.batch_alter_table('login_sessions', schema=None) as batch_op:
        batch_op.drop_index(batch_op.f('ix_login_sessions_user_id'))
        batch_op.drop_index(batch_op.f('ix_login_sessions_expires_at'))

    op.drop_table('login_sessions')
    op.drop_table('users')
    op.drop_table('labs')
