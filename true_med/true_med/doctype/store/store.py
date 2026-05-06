# Copyright (c) 2026, Excel Technologies Ltd and contributors
# For license information, please see license.txt

import frappe
import requests
import time
from frappe.model.document import Document

GEOCODE_URL = 'https://nominatim.openstreetmap.org/search'
REQUEST_TIMEOUT = 8
MAX_RETRIES = 3


class Store(Document):
    def validate(self):
        self.full_address = self._build_full_address()
        if not self.full_address:
            return

        if not self._should_refresh_coordinates():
            return

        coordinates = self._get_coordinates_from_address(self.full_address)
        if not coordinates:
            return

        self.latitude = coordinates["latitude"]
        self.longitude = coordinates["longitude"]

    def _build_full_address(self) -> str:
        if self.full_address and self.full_address.strip():
            return self.full_address.strip()

        address_parts = [
            self.street_address,
            self.city,
            self.state,
            self.zip,
        ]
        return ", ".join([part.strip() for part in address_parts if part])

    def _should_refresh_coordinates(self) -> bool:
        if not self.latitude or not self.longitude:
            return True

        previous_doc = self.get_doc_before_save()
        if not previous_doc:
            return True

        watched_fields = ("street_address", "city", "state", "zip", "full_address")
        return any(self.get(field) != previous_doc.get(field)
                   for field in watched_fields)

    def _get_coordinates_from_address(self, address: str):
        params = {
            'q': address,
            'format': 'json',
            'limit': 1,
        }
        headers = {
            'User-Agent': 'true-med-store-geocoder/1.0',
            'Accept-Language': 'en',
        }
        contact_email = frappe.conf.get('error_report_email')
        if contact_email:
            params['email'] = contact_email

        for attempt in range(MAX_RETRIES):
            try:
                response = requests.get(
                    GEOCODE_URL,
                    params=params,
                    headers=headers,
                    timeout=REQUEST_TIMEOUT,
                )
                if response.status_code == 429:
                    retry_after = response.headers.get('Retry-After')
                    sleep_seconds = float(retry_after) if retry_after else 1.5
                    time.sleep(max(1.0, sleep_seconds))
                    continue

                response.raise_for_status()
                data = response.json()
                if not data:
                    return None

                return {
                    'latitude': data[0].get('lat'),
                    'longitude': data[0].get('lon'),
                }
            except Exception:
                if attempt < MAX_RETRIES - 1:
                    time.sleep(1.5 * (attempt + 1))
                    continue
                frappe.log_error(
                    title='Store Geocoding Failed',
                    message=f'Could not geocode address: {address}',
                )
                return None


@frappe.whitelist()
def backfill_store_coordinates(limit: int = 500) -> dict:
    limit = max(1, min(int(limit), 5000))
    stores = frappe.get_all(
        'Store',
        filters={'full_address': ['is', 'set']},
        fields=['name'],
        limit=limit,
        order_by='modified desc',
    )

    updated = 0
    skipped = 0
    for row in stores:
        store = frappe.get_doc('Store', row.name)
        if store.latitude and store.longitude:
            skipped += 1
            continue
        store.save(ignore_permissions=True)
        if store.latitude and store.longitude:
            updated += 1
        else:
            skipped += 1

    return {
        'updated': updated,
        'skipped': skipped,
        'processed': len(stores),
    }


def scheduled_backfill_store_coordinates():
    """Scheduler task to gradually fill missing store coordinates."""
    return backfill_store_coordinates(limit=100)
