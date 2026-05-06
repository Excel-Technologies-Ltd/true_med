# Copyright (c) 2026, Excel Technologies Ltd and contributors
# For license information, please see license.txt

import frappe
import requests
from frappe.model.document import Document


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
        try:
            response = requests.get(
                "https://nominatim.openstreetmap.org/search",
                params={
                    "q": address,
                    "format": "json",
                    "limit": 1,
                },
                headers={"User-Agent": "true-med-store-geocoder/1.0"},
                timeout=8,
            )
            response.raise_for_status()
            data = response.json()
        except Exception:
            frappe.log_error(
                title="Store Geocoding Failed",
                message=f"Could not geocode address: {address}",
            )
            return None

        if not data:
            return None

        return {
            "latitude": data[0].get("lat"),
            "longitude": data[0].get("lon"),
        }
