
import sqlite3

def create_database():
    conn = sqlite3.connect("smarthome.db")
    cursor = conn.cursor()

    cursor.execute("""
        CREATE TABLE IF NOT EXISTS sensor_data (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            temperature REAL,
            humidity REAL,
            light INTEGER,
            door INTEGER,
            power REAL,
            energy REAL,
            timestamp DATETIME DEFAULT CURRENT_TIMESTAMP
        )
    """)

    conn.commit()
    conn.close()

    print("Database and table created successfully!")

if __name__ == "__main__":
    create_database()