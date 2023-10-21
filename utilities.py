import re
import os
import requests
from os.path import join, exists

def is_valid_category(category):
    pattern = re.compile(r'^[a-zA-Z0-9À-ÖØ-öø-ÿ\s,]+$')
    return bool(pattern.match(category))

def get_game_id(filename):
    if '[' in filename and ']' in filename:
        game_id = filename.split('[')[1].split(']')[0]
        return game_id
    else:
        return None

def download_cover(game):
    image_url = game['iconUrl']
    
    if image_url is None:
        return
    
    image_filename = os.path.join("static/images", f"{game['id']}-cover.jpg")
    
    os.makedirs(os.path.dirname(image_filename), exist_ok=True)

    if not os.path.exists(image_filename):
        print(f"Downloading cover image for {game['name']} (ID: {game['id']})")
        response = requests.get(image_url, stream=True)

        if response.status_code == 200:
            with open(image_filename, 'wb') as f:
                f.write(response.content)
 
def format_release_date(date):
    return f"{date[:4]}/{date[4:6]}/{date[6:]}"

def remove_empty_folders(path):
    items = os.listdir(path)
    
    only_dot_items = all(name.startswith('.') for name in items)  # Check if all items in the directory are dot files or folders

    if not items or only_dot_items:
        for name in items:
            os.remove(os.path.join(path, name))
        os.rmdir(path)
        return True

    # If the folder is not empty, check its subfolders
    removed_subfolder = False
    for root, dirs, files in os.walk(path, topdown=False):
        for name in dirs:
            dir_path = os.path.join(root, name)
            if remove_empty_folders(dir_path):
                removed_subfolder = True

    return removed_subfolder

def find_name_in_json(filename, json_data):
    
    def search_by_delimiter(delimiter):
        name_parts = filename.split(delimiter)
        search_name = delimiter.join(name_parts)
        
        while search_name:
            for key, value in json_data.items():  # Iterate over the JSON data to find a match
                if value.get('name') and value.get('name').lower() == search_name.lower():
                    return value['name']  # Return the name found in the JSON data
            name_parts = name_parts[:-1]
            search_name = delimiter.join(name_parts)  # If not found, strip the last section of the name and search again
        
        return None

    # First, try searching by space delimiter
    result = search_by_delimiter(' ')
    if result:
        return result
    
    return search_by_delimiter('_') # If no result found, try searching by underscore delimiter