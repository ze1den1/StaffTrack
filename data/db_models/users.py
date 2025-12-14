from datetime import datetime

from flask_login import UserMixin
import sqlalchemy as sa
from sqlalchemy import orm
from sqlalchemy_serializer import SerializerMixin
from .db_session import SqlAlchemyBase


class User(SqlAlchemyBase, UserMixin, SerializerMixin):
    __tablename__ = 'users'

    id = sa.Column(sa.Integer, primary_key=True)
    username = sa.Column(sa.String(80), unique=True, nullable=False)
    hashed_password = sa.Column(sa.String(200), nullable=False)
    name = sa.Column(sa.String(100), nullable=False)

    email = sa.Column(sa.String, nullable=True)
    phone_number = sa.Column(sa.String, nullable=True)
    department = sa.Column(sa.String, nullable=True)
    post = sa.Column(sa.String, nullable=True)

    role = sa.Column(sa.String(20), nullable=False)  # 'admin' или 'worker'
    created_at = sa.Column(sa.DateTime, default=datetime.now)
