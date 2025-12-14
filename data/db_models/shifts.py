import sqlalchemy as sa
from sqlalchemy import orm
from sqlalchemy_serializer import SerializerMixin

from .db_session import SqlAlchemyBase
from .users import User


class Shift(SqlAlchemyBase, SerializerMixin):
    __tablename__ = 'shift'

    id = sa.Column(sa.Integer, primary_key=True)
    user_id = sa.Column(sa.Integer, sa.ForeignKey(User.id), nullable=False)
    start_time = sa.Column(sa.DateTime, nullable=False)
    end_time = sa.Column(sa.DateTime)
    duration = sa.Column(sa.Float)  # в часах

    user = orm.relationship('User', backref=orm.backref('shifts', lazy=True))
