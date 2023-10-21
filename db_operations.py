from models import db, Platform, Category, Publisher, Language, GameCategory, GameLanguage, Update, DLC, Game
import config
import os
import json
from models import Platform, Category, Publisher, Language, GameCategory, GameLanguage, Update, DLC, Game
import re
from utilities import is_valid_category, get_game_id, download_cover, format_release_date, remove_empty_folders, find_name_in_json
from os.path import join, exists
from werkzeug.utils import secure_filename
import shutil
import hashlib

def add_to_db(entry):
    try:
        db.session.add(entry)
        db.session.commit()
    except Exception as e:
        db.session.rollback()

def delete_non_existent_files(model, attribute):
    entries = model.query.all()
    for entry in entries:
        path = os.path.join(getattr(entry, 'location'), getattr(entry, attribute))
        if not os.path.exists(path):
            db.session.delete(entry)
    db.session.commit()

def compute_file_hash(file_path):
    # Compute the SHA256 hash of a file
    sha256_hash = hashlib.sha256()
    with open(file_path,"rb") as f:
        for byte_block in iter(lambda: f.read(4096),b""):
            sha256_hash.update(byte_block)
    return sha256_hash.hexdigest()

def fetch_data():
    platforms = {p.name: p for p in Platform.query.all()}
    categories = {c.name: c for c in Category.query.all()}
    publishers = {p.name: p for p in Publisher.query.all()}
    languages = {l.name: l for l in Language.query.all()}
    return platforms, categories, publishers, languages

def move_or_delete(src, dest):
    # Handle the logic of moving or deleting files
    if os.path.exists(dest) and compute_file_hash(src) == compute_file_hash(dest):
        os.remove(src)
    else:
        shutil.move(src, dest)

def sanitize_filename(filename):
    return re.sub(r'[^A-Za-z0-9_. -]', '', filename)

def process_items(items, parent_dir, item_type, parent=None):
    os.makedirs(parent_dir, exist_ok=True)
    
    for item in items:
        full_file_path = os.path.join(item.location, item.filename)
        extension = item.filename.split('.')[-1]
        name = getattr(item, "name", item.id)
        
        # Check if the filename is already in the desired format
        pattern = re.compile(r'.*\[0100[0-9A-Fa-f]{12}\]\[v\d+\]\.' + extension)
        if pattern.match(item.filename):
            new_filename = item.filename
        else:
            # If the item is of type Update, fetch the main game's name
            if item_type == "update" and hasattr(item, "game") and item.game:
                name = item.game.name
            new_filename = f"{sanitize_filename(name)}[{item.id}][v{item.version}].{extension}"

        dest_path = os.path.join(parent_dir, new_filename)
        
        if os.path.exists(full_file_path):
            if full_file_path != dest_path:
                move_or_delete(full_file_path, dest_path)
            item.location = parent_dir
            item.filename = new_filename  # Update the filename in the database
            db.session.commit()
        else:
            db.session.delete(item)
            db.session.commit()

def preview_process_items(items, parent_dir, item_type, parent=None):
    changes = []
    
    for item in items:
        full_file_path = os.path.join(item.location, item.filename)
        extension = item.filename.split('.')[-1]
        name = getattr(item, "name", item.id)
        
        # Check if the filename is already in the desired format
        pattern = re.compile(r'.*\[0100[0-9A-Fa-f]{12}\]\[v\d+\]\.' + extension)
        if pattern.match(item.filename):
            new_filename = item.filename
        else:
            # If the item is of type Update, fetch the main game's name
            if item_type == "update" and hasattr(item, "game") and item.game:
                name = item.game.name
            new_filename = f"{sanitize_filename(name)}[{item.id}][v{item.version}].{extension}"

        dest_path = os.path.join(parent_dir, new_filename)
        
        if os.path.exists(full_file_path):
            if full_file_path != dest_path:
                changes.append(f"MOVE {full_file_path} to {dest_path}")
            else:
                changes.append(f"SET LOCATION {item.filename} to {parent_dir}")
        else:
            changes.append(f"DELETE {item_type} : {item.filename} from database")

    return changes

def handle_dlc(data, game_id, root, file):
    dlc_info = data.get(game_id)

    if dlc_info:
        existing_dlc_by_filename = DLC.query.filter_by(filename=file).first()  # Check if a DLC with the same filename already exists in the database

        if existing_dlc_by_filename:
            return

        possible_game_ids = [key for key in data if key.startswith(game_id[:12]) and not key.endswith("800")]  # Look for the associated main game in the JSON data
        associated_game_id = possible_game_ids[0] if possible_game_ids else None
        dlc = DLC(
            id=dlc_info['id'],
            name=dlc_info['name'],
            game_id=associated_game_id, 
            version=dlc_info['version'],
            location=root,
            filename=file
        )
        try:
            db.session.add(dlc)
            db.session.commit()
        except IntegrityError:
            db.session.rollback()
       
def handle_update(data, game_id, filename, root, file):
    main_game_id = game_id[:-3] + "000"
    version = int(filename.split('[')[2].split(']')[0].replace('v', ''))  # Extract version from filename
    update_info = data.get(game_id)
    
    if update_info:
        existing_update_by_filename = Update.query.filter_by(filename=file).first()  # Check if an update with the same filename already exists in the database
        if existing_update_by_filename:
            return
        
        existing_update = Update.query.filter_by(id=update_info['id'], version=version).first()  # Check if the update with the same ID and version already exists in the database
        if not existing_update:
            update = Update(
                id=update_info['id'], 
                game_id=main_game_id, 
                version=version,
                location=root,
                filename=file
            )
            try:
                db.session.add(update)
                db.session.commit()
            except IntegrityError:
                db.session.rollback()
        else:
            if existing_update.location != root or existing_update.filename != file:
                os.remove(os.path.join(root, file))
            else:
                existing_update.location = root
                existing_update.filename = file
                db.session.commit()

def handle_maingame(data, game_id, filename, root, file, platforms, publishers, categories, languages):
    main_game_id = game_id
    game_info = data.get(main_game_id)

    if not game_info:
        return

    download_cover(game_info)
    game_info['localIconUrl'] = f"static/images/{game_info['id']}-cover.jpg"
    game_info['releaseDate'] = format_release_date(str(game_info['releaseDate']))

    existing_game = Game.query.get(game_info['id'])
    if not existing_game and not game_id.endswith("800"):  # If not existing and not an update
        platform = None
        publisher = None
        game_categories = None
        game_languages = None
        
        # Handle platform
        platform_name = game_info.get('platform')
        if platform_name:
            platform = platforms.get(platform_name)
            if not platform:
                platform = Platform(id=platform_name, name=platform_name)
                db.session.add(platform)
                platforms[platform_name] = platform
        
        # Handle publisher
        publisher_name = game_info.get('publisher')
        if publisher_name:
            publisher = publishers.get(publisher_name)
            if not publisher:
                publisher = Publisher(name=publisher_name)
                db.session.add(publisher)
                publishers[publisher_name] = publisher 

        # Handle categories
        game_categories = []
        for category_name in (game_info.get('category') or []):
            if not is_valid_category(category_name):
                continue
            
            category = categories.get(category_name)
            if not category:
                category = Category(name=category_name)
                db.session.add(category)
                categories[category_name] = category 
            existing_game_category = GameCategory.query.filter_by(game_id=game_info['id'], category_id=category.id).first()  # Check if this category is already associated with the game
            if not existing_game_category:
                game_categories.append(category)

        # Handle languages
        game_languages = []
        languages_data = game_info.get('languages')
        if languages_data is not None:
            for language_name in set(languages_data):
                language = languages.get(language_name)
                if not language:
                    language = Language(name=language_name)
                    db.session.add(language)
                    languages[language_name] = language 
                game_languages.append(language)

        if game_info['name'] is not None:
            game = Game(
                id=game_info['id'],
                name=game_info['name'],
                localIconUrl=game_info['localIconUrl'],
                description=game_info['description'],
                developer=game_info.get('developer'),
                numberOfPlayers=game_info['numberOfPlayers'],
                rank=game_info['rank'],
                rating=game_info['rating'],
                releaseDate=game_info['releaseDate'],
                rightsId=game_info.get('rightsId'),
                size=game_info['size'],
                version=game_info['version'],
                filename=file,
                location=root,
                platform=platform.id if platform else None,
                categories=game_categories,
                languages=game_languages,
                publisher=publisher.name if publisher else None
            )

        try:
            db.session.add(game)
            db.session.commit()
        except Exception as e:
            db.session.rollback()

def handle_game_name_found(data, game_name, filename, file, root):
    game_id = next((key for key, value in data.items() if value.get('name') == game_name), None)  # Find the game ID from the JSON using the game name

    if not game_id:
        return

    main_game_id = game_id
    game_info = data.get(main_game_id)

    if not game_info:
        return

    download_cover(game_info)
    game_info['localIconUrl'] = f"static/images/{game_info['id']}-cover.jpg"
    game_info['releaseDate'] = format_release_date(str(game_info['releaseDate']))
    existing_game = Game.query.get(game_info['id'])

    if not existing_game:
        game = Game(
            id=game_info['id'],
            name=game_info['name'],
            localIconUrl=game_info['localIconUrl'],
            description=game_info['description'],
            developer=game_info.get('developer'),
            numberOfPlayers=game_info['numberOfPlayers'],
            rank=game_info['rank'],
            rating=game_info['rating'],
            releaseDate=game_info['releaseDate'],
            rightsId=game_info.get('rightsId'),
            size=game_info['size'],
            version=game_info['version'],
            filename=file,
            location=root,
        )
        try:
            db.session.add(game)
            db.session.commit()
        except Exception as e:
            db.session.rollback()
    else:
        print(f"Game Already Exist in db {game_name}")

def refresh_data_db():
    unprocessed_files = []

    if not os.path.isfile('titles.json'):
        r = requests.get(config.TINFOIL_URL)  # Download json file
        with open('titles.json', 'wb') as f:
            f.write(r.content)

    with open('titles.json') as json_file:
        data = json.load(json_file)

    # Recursively check all directories and files
    for root, dirs, files in os.walk(config.BASE_PATH):
        for file in files:
            filename, ext = os.path.splitext(file)
            if ext.lower() in [".nsp", ".nsz", ".xci", ".xcz"]:
                pattern = r'.*\[(0100[0-9A-Fa-f]{12})\]\[v\d+\]'
                match = re.match(pattern, filename)
                game_id = match.group(1) if match else None
                
                if game_id:
                    is_maingame = game_id.endswith("000")
                    is_update = game_id.endswith("800")
                    is_dlc = not (is_maingame or is_update)

                    if is_dlc:
                        handle_dlc(data, game_id, root, file)
                    elif is_update:
                        handle_update(data, game_id, filename, root, file)
                    elif is_maingame:
                        platforms, categories, publishers, languages = fetch_data()
                        handle_maingame(data, game_id, filename, root, file, platforms, publishers, categories, languages)
                else:  
                    existing_game_by_filename = Game.query.filter_by(filename=file).first()  
                    if existing_game_by_filename:
                        continue

                    game_name = find_name_in_json(filename, data)  
                    if game_name:
                        handle_game_name_found(data, game_name, filename, file, root)
                    unprocessed_files.append(file)

    # Deleting non-existent entries
    delete_non_existent_files(Game, 'filename')
    delete_non_existent_files(Update, 'filename')
    delete_non_existent_files(DLC, 'filename')

    db.session.commit()

    return {
        'refreshed': [game.filename for game in Game.query.all()],
        'unprocessed': unprocessed_files
    }

def organize(games=None):
    if games is None:
        games = Game.query.all()

    for game in games:
        # For the main game
        game_dir = os.path.join(config.BASE_PATH, secure_filename(game.name))
        if os.path.exists(os.path.join(game.location, game.filename)):
            os.makedirs(game_dir, exist_ok=True)
            process_items([game], game_dir, "game")

        # For updates
        updates = [update for update in game.updates if os.path.exists(os.path.join(update.location, update.filename))]
        if updates:
            update_dir = os.path.join(game_dir, "update")
            os.makedirs(update_dir, exist_ok=True)
            process_items(updates, update_dir, "update", game)

        # For DLCs
        dlcs = [dlc for dlc in game.dlcs if os.path.exists(os.path.join(dlc.location, dlc.filename))]
        if dlcs:
            dlc_dir = os.path.join(game_dir, "dlc")
            os.makedirs(dlc_dir, exist_ok=True)
            process_items(dlcs, dlc_dir, "dlc", game)

    # Collect the IDs of all updates and DLCs that are associated with a main game
    associated_update_ids = [update.id for game in games for update in game.updates]
    associated_dlc_ids = [dlc.id for game in games for dlc in game.dlcs]

    # Filter out the updates and DLCs that are already associated with a main game
    all_updates = Update.query.all()
    parentless_updates = [update for update in all_updates if update.id not in associated_update_ids]
    if parentless_updates:
        process_items(parentless_updates, config.PARENTLESS_UPDATES_DIR, "update")

    all_dlcs = DLC.query.all()
    parentless_dlcs = [dlc for dlc in all_dlcs if dlc.id not in associated_dlc_ids]
    if parentless_dlcs:
        process_items(parentless_dlcs, config.PARENTLESS_DLCS_DIR, "dlc")
        
    remove_empty_folders(config.BASE_PATH)

def preview_organize(games=None):
    changes = []

    if games is None:
        games = Game.query.all()

    for game in games:
        # For the main game
        game_dir = os.path.join(config.BASE_PATH, secure_filename(game.name))
        if os.path.exists(os.path.join(game.location, game.filename)):
            changes.extend(preview_process_items([game], game_dir, "game"))

        # For updates
        updates = [update for update in game.updates if os.path.exists(os.path.join(update.location, update.filename))]
        if updates:
            update_dir = os.path.join(game_dir, "update")
            changes.extend(preview_process_items(updates, update_dir, "update", game))

        # For DLCs
        dlcs = [dlc for dlc in game.dlcs if os.path.exists(os.path.join(dlc.location, dlc.filename))]
        if dlcs:
            dlc_dir = os.path.join(game_dir, "dlc")
            changes.extend(preview_process_items(dlcs, dlc_dir, "dlc", game))

    # Collect the IDs of all updates and DLCs that are associated with a main game
    associated_update_ids = [update.id for game in games for update in game.updates]
    associated_dlc_ids = [dlc.id for game in games for dlc in game.dlcs]

    # Filter out the updates and DLCs that are already associated with a main game
    all_updates = Update.query.all()
    parentless_updates = [update for update in all_updates if update.id not in associated_update_ids]
    if parentless_updates:
        changes.extend(preview_process_items(parentless_updates, config.PARENTLESS_UPDATES_DIR, "update"))

    all_dlcs = DLC.query.all()
    parentless_dlcs = [dlc for dlc in all_dlcs if dlc.id not in associated_dlc_ids]
    if parentless_dlcs:
        changes.extend(preview_process_items(parentless_dlcs, config.PARENTLESS_DLCS_DIR, "dlc"))

    return changes

def delete_game_db(gameId=None):
    if gameId is None:
        gameId = request.args.get('gameId')
    
    game = Game.query.get(gameId)
    
    if game:
        game_path = os.path.join(game.location, game.filename)

        if os.path.exists(game_path):
            os.remove(game_path)

        db.session.delete(game)
        db.session.commit()
    
def delete_update_db(updateId=None):
    if updateId is None:
        updateId = request.args.get('updateId')
    
    update = Update.query.get(updateId)
    game_id = update.game_id if update else None
    
    if update:
        update_path = os.path.join(update.location, update.filename)
        
        if os.path.exists(update_path):
            os.remove(update_path)

        db.session.delete(update)
        db.session.commit()
    

def delete_dlc_db(dlcId=None):
    if dlcId is None:
        dlcId = request.args.get('dlcId')
    
    dlc = DLC.query.get(dlcId)
    game_id = dlc.game_id if dlc else None
    
    if dlc:
        dlc_path = os.path.join(dlc.location, dlc.filename)

        if os.path.exists(dlc_path):
            os.remove(dlc_path)
        
        db.session.delete(dlc)
        db.session.commit()