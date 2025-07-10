if __name__ == '__main__':
    import os
    import sys
    sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
    from database import DatabaseManager

    db_path = '../news_pipeline.db'
    # Initialize the database manager
    db_manager = DatabaseManager(db_path)

    # Initialize the database
    db_manager.init_database()
    checked_tables = db_manager.check_tables()

    print("Database initialized successfully.")   