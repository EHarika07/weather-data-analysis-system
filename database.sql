create database weather_db;

use weather_db;

create table weather_records(
    record_id int auto_increment primary key,
    observation_date date,
    location varchar(100),
    temperature decimal(5,2),
    humidity decimal(5,2),
    rainfall decimal(8,2)
);