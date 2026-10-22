CREATE TABLE IF NOT EXISTS sensor_readings (
    id SERIAL PRIMARY KEY,
    pond_id INT,
    timestamp TIMESTAMPTZ,
    dissolved_oxygen REAL,
    ph REAL,
    water_temperature REAL,
    salinity REAL
);

CREATE TABLE IF NOT EXISTS ponds (
    id INT PRIMARY KEY,
    name VARCHAR(100) NOT NULL,
    status VARCHAR(20) DEFAULT 'active',
    metadata JSONB
);

CREATE TABLE IF NOT EXISTS predictions (
    id SERIAL PRIMARY KEY,
    pond_id INT REFERENCES ponds(id) ON DELETE CASCADE,
    model_used VARCHAR(50),
    parameter VARCHAR(50),
    predicted_value NUMERIC(6, 2),
    prediction_time TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    target_time TIMESTAMP
);
