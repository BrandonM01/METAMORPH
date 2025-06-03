"""Add billing & referral fields to User

Revision ID: b6e960b45c1b
Revises: 
Create Date: 2025-05-04 12:13:14.005911

"""
from alembic import op
import sqlalchemy as sa

# revision identifiers, used by Alembic.
revision = 'b6e960b45c1b'
down_revision = None
branch_labels = None
depends_on = None

def upgrade():
    # Add each column in a separate block to avoid circular dependency issues
    with op.batch_alter_table('user', schema=None) as batch_op:
        batch_op.add_column(sa.Column('stripe_customer_id', sa.String(length=100), nullable=True))
    with op.batch_alter_table('user', schema=None) as batch_op:
        batch_op.add_column(sa.Column('stripe_subscription_id', sa.String(length=100), nullable=True))
    with op.batch_alter_table('user', schema=None) as batch_op:
        batch_op.add_column(sa.Column('plan', sa.String(length=50), nullable=True))
    with op.batch_alter_table('user', schema=None) as batch_op:
        batch_op.add_column(sa.Column('tokens', sa.Integer(), nullable=True))
    with op.batch_alter_table('user', schema=None) as batch_op:
        batch_op.add_column(sa.Column('referral_code', sa.String(length=20), nullable=True))
    with op.batch_alter_table('user', schema=None) as batch_op:
        batch_op.add_column(sa.Column('referred_by_id', sa.Integer(), nullable=True))
    # Now alter columns
    with op.batch_alter_table('user', schema=None) as batch_op:
        batch_op.alter_column('email',
            existing_type=sa.VARCHAR(length=150),
            nullable=False)
        batch_op.alter_column('password',
            existing_type=sa.VARCHAR(length=150),
            nullable=False)
    # Add constraints in separate blocks
    with op.batch_alter_table('user', schema=None) as batch_op:
        batch_op.create_unique_constraint('uq_user_referral_code', ['referral_code'])
    with op.batch_alter_table('user', schema=None) as batch_op:
        batch_op.create_foreign_key('fk_user_referred_by_id', 'user', ['referred_by_id'], ['id'])

def downgrade():
    # Drop constraints first
    with op.batch_alter_table('user', schema=None) as batch_op:
        batch_op.drop_constraint('fk_user_referred_by_id', type_='foreignkey')
    with op.batch_alter_table('user', schema=None) as batch_op:
        batch_op.drop_constraint('uq_user_referral_code', type_='unique')
    # Then revert column changes
    with op.batch_alter_table('user', schema=None) as batch_op:
        batch_op.alter_column('password',
            existing_type=sa.VARCHAR(length=150),
            nullable=True)
        batch_op.alter_column('email',
            existing_type=sa.VARCHAR(length=150),
            nullable=True)
    # Then drop columns one at a time
    with op.batch_alter_table('user', schema=None) as batch_op:
        batch_op.drop_column('referred_by_id')
    with op.batch_alter_table('user', schema=None) as batch_op:
        batch_op.drop_column('referral_code')
    with op.batch_alter_table('user', schema=None) as batch_op:
        batch_op.drop_column('tokens')
    with op.batch_alter_table('user', schema=None) as batch_op:
        batch_op.drop_column('plan')
    with op.batch_alter_table('user', schema=None) as batch_op:
        batch_op.drop_column('stripe_subscription_id')
    with op.batch_alter_table('user', schema=None) as batch_op:
        batch_op.drop_column('stripe_customer_id')
