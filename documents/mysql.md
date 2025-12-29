## Create a Database

create database consumer_affairs_db DEFAULT CHARSET = utf8mb4 DEFAULT COLLATE = utf8mb4_unicode_ci;

## Create a User

CREATE USER 'doca'@'localhost' IDENTIFIED WITH mysql_native_password by 'Doca@321';

## Permit user to access the database

grant all privileges on consumer_affairs_db.* to 'doca'@'localhost' with grant option;

