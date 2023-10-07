from flask import Flask, render_template, request, redirect, url_for, jsonify
from sqlalchemy import text, or_
from os.path import join
import config
from models import db, Platform, Category, Publisher, Language, GameCategory, GameLanguage, Update, DLC, Game
from db_operations import refresh_data_db, organize, delete_game_db, delete_update_db, delete_dlc_db
import os
import requests
import json

app = Flask(__name__)
app.config['SQLALCHEMY_DATABASE_URI'] = config.SQLALCHEMY_DATABASE_URI
db.init_app(app)

global_titles_data = None

@app.route('/game/<game_id>')
def game_detail(game_id):
    game = Game.query.get(game_id)
    if not game:
        return "Game not found", 404
    print(game.dlcs)
    return render_template('game_detail.html', game=game)

@app.route('/refresh', methods=['POST'])
def refresh_data():
    result = refresh_data_db()
    return redirect(url_for('home'))

@app.route('/organize', methods=['GET', 'POST'])
def organize_data():
    result = organize()
    return redirect(url_for('home'))

@app.route('/api/games')
def api_games():
    global global_titles_data
    
    page = request.args.get('page', 1, type=int)
    per_page = request.args.get('per_page', 50, type=int)
    category = request.args.get('category')
    sort = request.args.get('sort', 'name')  # default sort by name
    search_query = request.args.get('search_query', '').strip()
    missing_updates_filter = request.args.get('missingUpdates') == 'true'

    query = db.session.query(Game)

    if search_query:   # Apply search filter if there's a search query
        query = query.filter(
            or_(
                Game.name.ilike(f"%{search_query}%"),
                Game.id.ilike(f"%{search_query}%")
            )
        )
        
    if category and category != "All":  # Apply category filter if it's not 'All'
        query = query.join(GameCategory).join(Category).filter(Category.name == category)

    # Apply sorting based on the 'sort' parameter
    if sort == 'releaseDate':
        query = query.order_by(Game.releaseDate.desc())
    elif sort == 'rank':
        query = query.order_by(Game.rank)
    elif sort == 'name':
        query = query.order_by(Game.name)

    games = query.limit(per_page).offset((page - 1) * per_page).all()  # Get the games

    if missing_updates_filter:
        games_with_missing_updates = set()

        for game in games:
            for update in game.updates:
                latest_version_from_json = global_titles_data.get(update.id, {}).get('version', None)

                # If the version data is missing from the JSON or if the update's version is less than the JSON version,
                # then it's missing an update and the game should be included
                if latest_version_from_json is not None and update.version < int(latest_version_from_json):
                    games_with_missing_updates.add(game)


        games = list(games_with_missing_updates)  # Convert set back to list


    return jsonify({
        'games': [game.to_dict() for game in games]
    })

@app.route('/delete_game')
def delete_game():
    result = delete_game_db()
    return redirect(url_for('home'))

@app.route('/delete_update')
def delete_update():
    result = delete_update_db()
    return redirect(url_for('game_detail', game_id=game_id))

@app.route('/delete_dlc')
def delete_dlc():
    result = delete_dlc_db()
    return redirect(url_for('game_detail', game_id=game_id))

@app.route('/', methods=['GET', 'POST'])
def home():
    global global_titles_data

    # Fetch counts
    total_games = Game.query.count()
    total_updates = Update.query.count()
    total_dlcs = DLC.query.count()

    # Fetch sort option and determine sort column
    sort_option = request.args.get('sort', 'name')
    if sort_option == 'releaseDate':
        sort_column = Game.releaseDate.desc()
    elif sort_option == 'rank':
        sort_column = Game.rank.asc()
    else:  # default to 'name'
        sort_column = Game.name.asc()

    # Start building the game query
    games_query = Game.query.order_by(sort_column)
    
    # Check for category filter
    selected_category = request.args.get('category')
    if selected_category and selected_category != "All":
        games_query = games_query.join(Game.game_categories).join(GameCategory.category).filter(Category.name == selected_category)

    # Handle pagination
    page = request.args.get('page', 1, type=int)
    paged_games = games_query.paginate(page=page, per_page=50, error_out=False)

    # Compute missing_updates_count for the selected category
    games_to_check = games_query.all()  # Fetch games of the selected category
    missing_updates_count = 0

    # Load the JSON file for version checking
    if not os.path.isfile('titles.json'):
        r = requests.get(config.TINFOIL_URL)
        with open('titles.json', 'wb') as f:
            f.write(r.content)

    with open('titles.json') as f:
        global_titles_data = json.load(f)

    for game in games_to_check:
        update_id = game.id[:-3] + "800"
        latest_version_from_json = global_titles_data.get(update_id, {}).get('version', 'No updates')
        latest_update_version = game.get_latest_update_version()
        if latest_update_version != latest_version_from_json:
            missing_updates_count += 1

    # Fetch all categories for the dropdown
    all_categories = Category.query.all()

    if request.headers.get('X-Requested-With') == 'XMLHttpRequest':
        return jsonify([game.to_dict() for game in paged_games.items])

    return render_template('home.html', games=paged_games.items, categories=all_categories, selected_category=selected_category, total_games=total_games, total_updates=total_updates, missing_updates_count=missing_updates_count, total_dlcs=total_dlcs)

if __name__ == '__main__':
    with app.app_context():
        db.create_all()
    app.run(host='0.0.0.0', debug=True, port=5001)
