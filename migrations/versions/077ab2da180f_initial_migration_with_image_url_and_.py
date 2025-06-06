"""Initial migration with image_url and ticket_request

Revision ID: 077ab2da180f
Revises: 
Create Date: 2025-05-29 18:14:36.200952

"""
from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision = '077ab2da180f'
down_revision = None
branch_labels = None
depends_on = None


def upgrade():
    # ### commands auto generated by Alembic - please adjust! ###
    with op.batch_alter_table('event', schema=None) as batch_op:
        batch_op.add_column(sa.Column('image_url', sa.String(length=200), nullable=True))

    with op.batch_alter_table('ticket_request', schema=None) as batch_op:
        batch_op.add_column(sa.Column('dob', sa.Date(), nullable=True))
        batch_op.add_column(sa.Column('otp', sa.String(length=6), nullable=True))
        batch_op.add_column(sa.Column('verified', sa.Boolean(), nullable=True))

    # ### end Alembic commands ###


def downgrade():
    # ### commands auto generated by Alembic - please adjust! ###
    with op.batch_alter_table('ticket_request', schema=None) as batch_op:
        batch_op.drop_column('verified')
        batch_op.drop_column('otp')
        batch_op.drop_column('dob')

    with op.batch_alter_table('event', schema=None) as batch_op:
        batch_op.drop_column('image_url')

    # ### end Alembic commands ###
