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
    # Step 1: Add columns and alter columns (NO constraints)
    with op.batch_alter_table('user', schema=None) as batch_op:
        batch_op.add_column(sa.Column('stripe_customer_id', sa.String(length=100), nullable=True))
        batch_op.add_column(sa.Column('stripe_subscription_id', sa.String(length=100), nullable=True))
        batch_op.add_column(sa.Column('plan', sa.String(length=50), nullable=True))
        batch_op.add_column(sa.Column('tokens', sa.Integer(), nullable=True))
        batch_op.add_column(sa.Column('referral_code', sa.String(length=20), nullable=True))
        batch_op.add_column(sa.Column('referred_by_id', sa.Integer(), nullable=True))
        batch_op.alter_column('email',
               existing_type=sa.VARCHAR(length=150),
               nullable=False)
        batch_op.alter_column('password',
               existing_type=sa.VARCHAR(length=150),
               nullable=False)
        # Do NOT create constraints here!

    # Step 2: Add constraints in a separate block
    with op.batch_alter_table('user', schema=None) as batch_op:
        batch_op.create_unique_constraint('uq_user_referral_code', ['referral_code'])
        batch_op.create_foreign_key('fk_user_referred_by_id', 'user', ['referred_by_id'], ['id'])

def downgrade():
    # Step 1: Drop constraints first
    with op.batch_alter_table('user', schema=None) as batch_op:
        batch_op.drop_constraint('fk_user_referred_by_id', type_='foreignkey')
        batch_op.drop_constraint('uq_user_referral_code', type_='unique')

    # Step 2: Drop columns and revert column changes
    with op.batch_alter_table('user', schema=None) as batch_op:
        batch_op.alter_column('password',
               existing_type=sa.VARCHAR(length=150),
               nullable=True)
        batch_op.alter_column('email',
               existing_type=sa.VARCHAR(length=150),
               nullable=True)
        batch_op.drop_column('referred_by_id')
        batch_op.drop_column('referral_code')
        batch_op.drop_column('tokens')
        batch_op.drop_column('plan')
        batch_op.drop_column('stripe_subscription_id')
        batch_op.drop_column('stripe_customer_id')
