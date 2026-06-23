import requests
import yaml
import config

def register_commands():
    # Load commands from gymbo_commands.yml
    try:
        with open("gymbo_commands.yml", "r") as file:
            commands = yaml.safe_load(file)
    except FileNotFoundError:
        print("Error: gymbo_commands.yml not found.")
        return
    except yaml.YAMLError as e:
        print(f"Error parsing gymbo_commands.yml: {e}")
        return

    # Check if necessary credentials are provided
    if not config.DISCORD_TOKEN or config.DISCORD_TOKEN == "your_bot_token_here":
        print("Error: Please set your DISCORD_TOKEN in config.py")
        return
    if not config.APPLICATION_ID or config.APPLICATION_ID == "your_application_id_here":
        print("Error: Please set your APPLICATION_ID in config.py")
        return

    headers = {
        "Authorization": f"Bot {config.DISCORD_TOKEN}",
        "Content-Type": "application/json"
    }

    # Register global commands (note: global commands can take up to an hour to cache/update on Discord)
    url = f"https://discord.com/api/v10/applications/{config.APPLICATION_ID}/commands"

    print(f"Registering {len(commands)} global commands to Discord...")

    # Make bulk overwrite request
    response = requests.put(url, headers=headers, json=commands)

    if response.status_code in [200, 201]:
        print("Successfully registered commands:")
        for cmd in response.json():
            print(f" - /{cmd['name']}: {cmd['description']} (ID: {cmd['id']})")
    else:
        print(f"Failed to register commands. Status code: {response.status_code}")
        print(f"Response: {response.text}")

if __name__ == "__main__":
    register_commands()