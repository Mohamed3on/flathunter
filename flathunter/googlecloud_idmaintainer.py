"""Storage back-end implementation using Google Cloud Firestore"""
import datetime

import firebase_admin
from firebase_admin import credentials
from firebase_admin import firestore

from flathunter.logging import logger
from flathunter.exceptions import PersistenceException


class GoogleCloudIdMaintainer:
    """Storage back-end - implementation of IdMaintainer API"""

    def __init__(self, config):
        project_id = config.google_cloud_project_id()
        if project_id is None:
            raise PersistenceException(
                "Need to project a google_cloud_project_id in config.yaml")
        firebase_admin.initialize_app(credentials.ApplicationDefault(), {
            'projectId': project_id
        })
        self.database = firestore.client()

    def mark_processed(self, expose_id):
        """Mark exposes as processed when we have processed them"""
        logger.debug('mark_processed(%d)', expose_id)
        self.database.collection('processed').document(
            str(expose_id)).set({'id': expose_id})

    def is_processed(self, expose_id):
        """Returns true if an expose has already been marked as processed"""
        logger.debug('is_processed(%d)', expose_id)
        doc = self.database.collection('processed').document(str(expose_id))
        return doc.get().exists

    def save_expose(self, expose):
        """Writes an expose to the storage backend"""
        now = datetime.datetime.now(tz=datetime.timezone.utc)
        record = expose.copy()
        record.update({'created_at': now,
                       'created_sort': (0 - now.timestamp())})
        self.database.collection('exposes').document(
            str(expose['id'])).set(record)

    def is_contacted(self, expose_id, crawler):
        """Returns true if a landlord has already been contacted for this expose"""
        doc = self.database.collection('contacted').document(
            f"{expose_id}_{crawler}").get()
        return doc.exists

    def mark_contacted(self, expose_id, crawler):
        """Mark an expose as contacted in the database"""
        self.database.collection('contacted').document(
            f"{expose_id}_{crawler}").set({
                'id': expose_id,
                'crawler': crawler,
                'contacted_at': datetime.datetime.now(tz=datetime.timezone.utc),
            })
