from os import path

# Database Configuration
SQLALCHEMY_DATABASE_URI = 'sqlite:///games.db'

# URL Configuration
TINFOIL_URL = 'https://tinfoil.media/repo/db/titles.json'

# Base Paths
BASE_PATH = './drive'
PARENTLESS_UPDATES_DIR = path.join(BASE_PATH, 'Parentless_Updates')
PARENTLESS_DLCS_DIR = path.join(BASE_PATH, 'Parentless_DLCs')
