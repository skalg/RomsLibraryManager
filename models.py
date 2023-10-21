from flask_sqlalchemy import SQLAlchemy
db = SQLAlchemy()

class Platform(db.Model):
    id = db.Column(db.String, primary_key=True)
    name = db.Column(db.String, nullable=False)

class Category(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    name = db.Column(db.String, nullable=False)

class Publisher(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    name = db.Column(db.String, nullable=False)

class Language(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    name = db.Column(db.String, nullable=False)

class GameCategory(db.Model):
    game_id = db.Column(db.String, db.ForeignKey('game.id'), primary_key=True)
    category_id = db.Column(db.Integer, db.ForeignKey('category.id'), primary_key=True)
    game = db.relationship('Game', backref=db.backref('game_categories', cascade="all, delete-orphan"))
    category = db.relationship('Category', backref='game_categories')

class GameLanguage(db.Model):
    game_id = db.Column(db.String, db.ForeignKey('game.id'), primary_key=True)
    language_id = db.Column(db.Integer, db.ForeignKey('language.id'), primary_key=True)
    game = db.relationship('Game', backref=db.backref('game_languages', cascade="all, delete-orphan"))
    language = db.relationship('Language', backref='game_languages')

class Update(db.Model):
    id = db.Column(db.String)
    game_id = db.Column(db.String, db.ForeignKey('game.id'))
    version = db.Column(db.Integer)
    filename = db.Column(db.String, primary_key=True)
    location = db.Column(db.String)
    game = db.relationship('Game', backref=db.backref('updates', lazy=True))

class DLC(db.Model):
    id = db.Column(db.String)
    name = db.Column(db.String, nullable=False)
    game_id = db.Column(db.String, db.ForeignKey('game.id'))
    version = db.Column(db.Integer)
    filename = db.Column(db.String, primary_key=True)
    location = db.Column(db.String)
    game = db.relationship('Game', backref=db.backref('dlcs', lazy=True))

class Game(db.Model):
    id = db.Column(db.String, primary_key=True)
    name = db.Column(db.String, nullable=False)
    localIconUrl = db.Column(db.String)
    description = db.Column(db.Text)
    developer = db.Column(db.String)
    language = db.Column(db.String)
    numberOfPlayers = db.Column(db.Integer)
    publisher = db.Column(db.String)
    rank = db.Column(db.Integer)
    rating = db.Column(db.Integer)
    ratingContent = db.Column(db.String)
    releaseDate = db.Column(db.String)
    rightsId = db.Column(db.String)
    size = db.Column(db.BigInteger)
    version = db.Column(db.Integer)
    platform_id = db.Column(db.String, db.ForeignKey('platform.id'))
    platform = db.relationship('Platform', backref='games')
    filename = db.Column(db.String(120))
    location = db.Column(db.String(120))
    categories = db.relationship('Category', secondary='game_category', backref=db.backref('games'))
    languages = db.relationship('Language', secondary='game_language', backref=db.backref('games'))
    def get_latest_update_version(self):
        return self.updates[-1].version if self.updates else 'No updates'
    def to_dict(self):
        return {
            'id': self.id,
            'name': self.name,
            'localIconUrl': self.localIconUrl,
            'description': self.description,
            'developer': self.developer,
            'numberOfPlayers': self.numberOfPlayers,
            'rank': self.rank,
            'rating': self.rating,
            'releaseDate': self.releaseDate if self.releaseDate else None,
            'rightsId': self.rightsId,
            'size': self.size,
            'version': self.version,
            'filename': self.filename,
            'location': self.location,
            'latest_update_version': self.get_latest_update_version(),
        }