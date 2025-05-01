from flask import current_app
from models import User, ConnectedService
from routes.Import.technofresh import Technofresh
from routes.Import.freshlinq import Freshlinq
from datetime import datetime, timedelta

def run_all_import_jobs():
    from main import app  # Import the app instance created by create_app()

    with app.app_context():
        print("Running scheduled import job...")

        start_date = "2024-10-01" # (datetime.now() - timedelta(days=14)).strftime("%Y-%m-%d")
        end_date = "2024-10-07" # datetime.now().strftime("%Y-%m-%d")
        
        users = User.query.join(ConnectedService).filter(
            ConnectedService.service_type == "Technofresh"
        ).all()

        for user in users:
            print(user)
            for message in Technofresh(user, start_date, end_date):
                print(message.strip())

        users = User.query.join(ConnectedService).filter(
            ConnectedService.service_type == "FreshLinq"
        ).all()

        start_date = "2024-12-01"

        for user in users:
            for message in Freshlinq(user, start_date):
                print(message.strip())
