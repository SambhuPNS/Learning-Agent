from google.cloud import firestore

from .config import GOOGLE_CLOUD_PROJECT

db = firestore.Client(project=GOOGLE_CLOUD_PROJECT or None)