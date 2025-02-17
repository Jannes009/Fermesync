import requests

# Start a session to maintain cookies
session = requests.Session()

# Define login credentials
login_url = "https://crm.technofresh.co.za/user/login"
payload = {
    "username": "your_username",  # Replace with the actual field name and your username
    "password": "your_password",  # Replace with the actual field name and your password
}

# Send login request
response = session.post(login_url, data=payload)

# Check if login was successful
if "dashboard" in response.url.lower():  # Adjust based on the URL after login
    print("Login successful!")

    # # URL of the file to download
    # file_url = "https://crm.technofresh.co.za/path/to/your/file.csv"

    # # Request the file
    # file_response = session.get(file_url)

    # # Save the file
    # if file_response.status_code == 200:
    #     with open("downloaded_file.csv", "wb") as file:
    #         file.write(file_response.content)
    #     print("File downloaded successfully!")
    # else:
    #     print("Failed to download the file.")

else:
    print("Login failed. Check credentials or additional form fields.")

