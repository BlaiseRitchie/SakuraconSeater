#!/usr/bin/env python3

import tornado.web
import json
import logging

import db
import util

log = logging.getLogger("mahjong")

class CurrentAnnouncementHandler(tornado.web.RequestHandler):
    def get(self):
        result = { 'status': "error",
                    'message': "Unknown error occurred"}
        with db.getCur() as cur:
            cur.execute("SELECT Message FROM Messages ORDER BY Date DESC LIMIT 1")
            result["status"] = "success"
            row = cur.fetchone()
            if row is not None:
                result["message"] = row[0]
            else:
                result["message"] = "No message at this time"
        self.write(json.dumps(result))
    def post(self):
        result = { 'status': "error",
                    'message': "Unknown error occurred"}
        announcement = self.get_argument("announcement", None)
        with db.getCur() as cur:
            cur.execute("INSERT INTO Messages VALUES(?, datetime('now', 'localtime'))", (announcement,))
            result = { 'status': "success",
                        'message': "Announcement updated"}
        self.write(json.dumps(result))

class TeachingSessionsHandler(tornado.web.RequestHandler):
    def get(self):
        result = { 'status': "error",
                    'message': "Unknown error occurred"}
        with db.getCur() as cur:
            cur.execute("SELECT Time FROM TeachingSessions ORDER BY Time ASC")
            result["status"] = "success"
            result["times"] = [{'Time':row[0]} for row in cur.fetchall()]
        self.write(json.dumps(result))
    def post(self):
        result = { 'status': "error",
                    'message': "Unknown error occurred"}
        time = self.get_argument("time", None)
        with db.getCur() as cur:
            cur.execute("INSERT INTO TeachingSessions(Time) VALUES(?)", (time,))
            result = { 'status': "success",
                        'message': "Teaching sessions updated"}
        self.write(json.dumps(result))

class DeleteTeachingSessionHandler(tornado.web.RequestHandler):
    def post(self):
        result = { 'status': "error",
                    'message': "Unknown error occurred"}
        time = self.get_argument("time", None)
        with db.getCur() as cur:
            cur.execute("DELETE FROM TeachingSessions WHERE Time = ?", (time,))
            result = { 'status': "success",
                        'message': "Teaching sessions updated"}
        self.write(json.dumps(result))
