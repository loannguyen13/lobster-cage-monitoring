
# Lobster Farming Monitoring System

## Overview
A smart lobster farming monitoring system integrating
water quality data, cloud services, and AI to support
aquaculture monitoring and decision-making.

## Current Progress
- Synthetic water quality dataset generation
- Water quality data analysis and visualization
- CSV sensor simulator, authenticated local MQTT and durable edge gateway
- Azure IoT Hub ingestion Function and additive PostgreSQL migration


## Project Structure
- `generate_dataset.py`: Generates synthetic water quality data
- `analyze_dataset.py`: Analyzes data and generates plots
- `lobster_cage_water_quality_synthetic.csv`: Synthetic dataset
- `dataset_timeseries.png`: Water quality time-series plots
- `event_label_distribution.png`: Event label distribution
- `event_labels_timeseries.png`: Event labels over time
- `edge/`: Everything running beside sensors: simulator, MQTT client/configuration, gateway and SQLite queue
- `backend/`: Azure Function, shared telemetry validation, database writer, CA download and deployment packaging
- `db/migrations/`: Additive schema migrations and device mapping
- `docker-compose.yml`: One Compose file for pgAdmin and the authenticated MQTT broker
- `requirements.txt`: One dependency list, grouped into edge, backend and research sections
- `tests/`: Unit tests and opt-in MQTT/PostgreSQL integration tests

## Dataset Disclaimer
The dataset is synthetic and intended for development
and testing. It does not represent real farm measurements.

## Team Responsibilities
- AI & Data (Kim Loan)
- Cloud & Backend (Phương Quyên)
- Frontend & Documentation (Như Hiếu)
