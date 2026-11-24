-- 闭站登记：站点临时关门的半开小时区间 [start_date start_hour, end_date end_hour)。
-- 闭站允许补登；闭站时段内已录入的归还记录原样保留，作为闭站冲突凭据，不做删除。
CREATE TABLE station_closures (
    id BIGINT PRIMARY KEY AUTO_INCREMENT,
    station_code VARCHAR(12) CHARACTER SET ascii COLLATE ascii_bin NOT NULL,
    start_date DATE NOT NULL,
    start_hour TINYINT UNSIGNED NOT NULL CHECK (start_hour < 24),
    end_date DATE NOT NULL,
    end_hour TINYINT UNSIGNED NOT NULL CHECK (end_hour < 24),
    reason VARCHAR(120) NOT NULL,
    created_at DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP,
    CONSTRAINT fk_closure_station FOREIGN KEY (station_code) REFERENCES stations(code),
    INDEX (station_code, start_date, start_hour),
    INDEX (start_date, end_date)
) CHARACTER SET utf8mb4;
