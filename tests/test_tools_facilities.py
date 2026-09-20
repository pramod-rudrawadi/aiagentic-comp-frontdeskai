"""Tests for Facilities domain tools: check_room_availability, book_meeting_room.

book_meeting_room takes the booker from the current_user_email ContextVar,
so tests act as an employee via ``_as()`` before booking.
"""

import os
import sys
import sqlite3
import pytest

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "app"))

TEST_DATE = "2026-12-15"   # future date unlikely to have conflicts


def _as(employee_id):
    """Act as this employee, the way the web app does — via the session ContextVar."""
    from auth import current_user_email
    return current_user_email.set(f"{employee_id}@test.com")


def _reset(token):
    from auth import current_user_email
    current_user_email.reset(token)


@pytest.fixture(autouse=True)
def setup_db(env):
    from tools import _get_db
    _get_db().close()
    import tools as t
    db = sqlite3.connect(t.TOOLS_DB)
    db.execute("""
        INSERT OR IGNORE INTO employees
            (employee_id, full_name, email, department, designation, date_of_join, is_active)
        VALUES ('EMP001', 'Dave Facilities', 'dave@test.com', 'Operations', 'Manager', '2022-01-01', 1)
    """)
    # Ensure at least one room exists
    db.execute("""
        INSERT OR IGNORE INTO meeting_rooms
            (room_id, room_name, capacity, floor, has_projector, has_whiteboard, has_video_conf, is_active)
        VALUES (1, 'Conference Room A', 10, 1, 1, 1, 0, 1)
    """)
    db.execute("""
        INSERT OR IGNORE INTO meeting_rooms
            (room_id, room_name, capacity, floor, has_projector, has_whiteboard, has_video_conf, is_active)
        VALUES (2, 'Board Room', 20, 2, 1, 1, 1, 1)
    """)
    db.commit()
    db.close()


class TestCheckRoomAvailability:
    def test_returns_available_rooms(self, env):
        from tools import check_room_availability
        result = check_room_availability.invoke({"date": TEST_DATE})
        assert isinstance(result, str) and len(result) > 0

    def test_filter_by_capacity(self, env):
        from tools import check_room_availability
        result = check_room_availability.invoke({"date": TEST_DATE, "min_capacity": 15})
        # Only Board Room (cap 20) should match
        assert "Board Room" in result or "20" in result

    def test_no_rooms_available_returns_message(self, env):
        from tools import book_meeting_room, check_room_availability
        token = _as("EMP001")
        try:
            # Book both rooms for the same slot
            book_meeting_room.invoke({
                "room_name": "Conference Room A",
                "date": "2026-11-01",
                "start_time": "10:00",
                "end_time": "11:00",
            })
            book_meeting_room.invoke({
                "room_name": "Board Room",
                "date": "2026-11-01",
                "start_time": "10:00",
                "end_time": "11:00",
            })
        finally:
            _reset(token)
        result = check_room_availability.invoke({
            "date": "2026-11-01",
            "start_time": "10:00",
            "end_time": "11:00",
        })
        assert isinstance(result, str)

    def test_with_time_filter(self, env):
        from tools import check_room_availability
        result = check_room_availability.invoke({
            "date": TEST_DATE,
            "start_time": "14:00",
            "end_time": "15:00",
        })
        assert isinstance(result, str)


class TestBookMeetingRoom:
    def test_book_available_room(self, env):
        from tools import book_meeting_room
        token = _as("EMP001")
        try:
            result = book_meeting_room.invoke({
                "room_name": "Conference Room A",
                "date": TEST_DATE,
                "start_time": "09:00",
                "end_time": "10:00",
                "purpose": "Sprint Planning",
                "attendees": 5,
            })
        finally:
            _reset(token)
        assert "confirmed" in result.lower() or "booked" in result.lower() or "success" in result.lower()

    def test_double_booking_rejected(self, env):
        from tools import book_meeting_room
        kwargs = {
            "room_name": "Conference Room A",
            "date": "2026-12-20",
            "start_time": "10:00",
            "end_time": "11:00",
        }
        token = _as("EMP001")
        try:
            book_meeting_room.invoke(kwargs)
            result2 = book_meeting_room.invoke(kwargs)
        finally:
            _reset(token)
        assert "unavailable" in result2.lower() or "already booked" in result2.lower() or "conflict" in result2.lower()

    def test_book_nonexistent_room(self, env):
        from tools import book_meeting_room
        token = _as("EMP001")
        try:
            result = book_meeting_room.invoke({
                "room_name": "Imaginary Room",
                "date": TEST_DATE,
                "start_time": "10:00",
                "end_time": "11:00",
            })
        finally:
            _reset(token)
        assert "not found" in result.lower() or "imaginary" in result.lower()

    def test_booking_stored_in_db(self, env):
        import tools as t
        from tools import book_meeting_room
        token = _as("EMP001")
        try:
            book_meeting_room.invoke({
                "room_name": "Board Room",
                "date": TEST_DATE,
                "start_time": "11:00",
                "end_time": "12:00",
                "purpose": "All Hands",
            })
        finally:
            _reset(token)
        db = sqlite3.connect(t.TOOLS_DB)
        row = db.execute(
            "SELECT * FROM room_bookings WHERE purpose='All Hands'"
        ).fetchone()
        db.close()
        assert row is not None