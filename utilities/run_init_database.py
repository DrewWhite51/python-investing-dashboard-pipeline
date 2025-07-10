if __name__ == '__main__':
    import os
    import sys
    sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
    from database import DatabaseManager

    # Ensure the database file exists
    db_path = '../news_pipeline.db'
    # if not os.path.exists(db_path):
    #     print(f"Database file '{db_path}' does not exist. Please run the application to create it.")
    #     sys.exit(1)

    # Initialize the database manager
    db_manager = DatabaseManager(db_path)

    # Initialize the database
    db_manager.init_database()
    checked_tables = db_manager.check_tables()

    print("Database initialized successfully.")   