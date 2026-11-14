from datetime import datetime
from unittest import mock
from zoneinfo import ZoneInfo

from django.core import mail
from django.test import TestCase
from django.urls import reverse

from accounts.models import Role, User

from . import services as svc
from .models import ChatSettings, Conversation, PublicHoliday

CAT = ZoneInfo("Africa/Gaborone")
TUESDAY_10AM = datetime(2026, 11, 17, 10, 0, tzinfo=CAT)
TUESDAY_5PM = datetime(2026, 11, 17, 17, 0, tzinfo=CAT)
SATURDAY_10AM = datetime(2026, 11, 21, 10, 0, tzinfo=CAT)
PW = "Strong-Pass-2026!"


def at(moment):
    return mock.patch("django.utils.timezone.now", return_value=moment)


class AvailabilityTests(TestCase):
    def setUp(self):
        self.agent = User.objects.create_user("kabo@example.bw", PW, first_name="Kabo", role=Role.CONSULTANT)
        self.agent2 = User.objects.create_user("lesedi@example.bw", PW, first_name="Lesedi", role=Role.CONSULTANT)

    def test_hours_weekends_and_holidays(self):
        with at(TUESDAY_10AM):
            svc.set_presence(self.agent, True)
            self.assertEqual(svc.availability()[0], "open")
        with at(TUESDAY_5PM):
            self.assertEqual(svc.availability()[0], "closed")
        with at(SATURDAY_10AM):
            self.assertEqual(svc.availability()[0], "closed")
        PublicHoliday.objects.create(date=TUESDAY_10AM.date(), name="Test holiday")
        with at(TUESDAY_10AM):
            self.assertEqual(svc.availability()[0], "closed")

    def test_no_agents_online_means_offline(self):
        with at(TUESDAY_10AM):
            state, msg = svc.availability()
        self.assertEqual(state, "offline")
        self.assertIn("No agent is available", msg)

    def test_busy_when_every_agent_is_full(self):
        ChatSettings.objects.update(max_chats_per_agent=2)
        with at(TUESDAY_10AM):
            svc.set_presence(self.agent, True)
            for _ in range(2):
                conv, _, _ = svc.start(guest_name="G", guest_email="g@example.bw", topic="Other", first_message="Hi")
                svc.accept(conv, self.agent)
            self.assertEqual(svc.availability()[0], "busy")
            svc.set_presence(self.agent2, True)  # a second agent with capacity reopens the service
            self.assertEqual(svc.availability()[0], "open")


class ChatFlowTests(TestCase):
    def setUp(self):
        self.agent = User.objects.create_user("kabo@example.bw", PW, first_name="Kabo", role=Role.CONSULTANT)
        self.client_user = User.objects.create_user("neo@example.bw", PW, first_name="Neo", role=Role.SUBMITTER, email_verified=True)

    def test_live_chat_between_client_and_agent(self):
        with at(TUESDAY_10AM):
            svc.set_presence(self.agent, True)
            self.client.force_login(self.client_user)
            self.client.post(reverse("chat:client"), {"topic": "Submitting an idea", "message": "How do I attach a PDF?"})
            conv = Conversation.objects.get()
            self.assertEqual((conv.status, conv.started_as), ("waiting", "open"))

            agent = self.client_class()
            agent.force_login(self.agent)
            state = agent.get(reverse("chat:state")).json()
            self.assertEqual([c["id"] for c in state["queue"]], [conv.pk])
            self.assertTrue(agent.post(reverse("chat:accept", args=[conv.pk])).json()["ok"])
            agent.post(reverse("chat:send", args=[conv.pk]), {"body": "Use the Supporting documents field."})

            msgs = self.client.get(reverse("chat:poll", args=[conv.pk])).json()["messages"]
            self.assertEqual([m["kind"] for m in msgs], ["customer", "system", "system", "agent"])
            self.assertEqual(msgs[-1]["body"], "Use the Supporting documents field.")

            self.client.post(reverse("chat:close", args=[conv.pk]))
            self.client.post(reverse("chat:rate", args=[conv.pk]), {"rating": "5"})
            conv.refresh_from_db()
            self.assertEqual((conv.status, conv.rating), ("closed", 5))

    def test_after_hours_guest_leaves_message_and_gets_email_reply(self):
        with at(TUESDAY_5PM):
            r = self.client.get(reverse("chat:client"))
            self.assertContains(r, "available from 09:00 to 16:00")
            self.client.post(reverse("chat:client"), {"name": "Thabo", "email": "thabo@example.bw", "topic": "CEDA financing", "message": "Do you fund startups?"})
        conv = Conversation.objects.get()
        self.assertEqual((conv.status, conv.started_as), ("offline", "closed"))
        with at(TUESDAY_10AM):
            svc.accept(conv, self.agent)
            svc.send(conv, self.agent, "Yes. Our team will follow up with details.", as_agent=True)
        self.assertEqual(mail.outbox[-1].to, ["thabo@example.bw"])

    def test_strangers_cannot_read_a_chat(self):
        conv, _, _ = svc.start(self.client_user, topic="Other", first_message="Private question")
        other = User.objects.create_user("x@example.bw", PW, role=Role.SUBMITTER)
        self.client.force_login(other)
        self.assertEqual(self.client.get(reverse("chat:poll", args=[conv.pk])).status_code, 403)
        self.assertEqual(self.client.get(reverse("chat:console")).status_code, 403)

    def test_agent_cannot_reply_in_another_agents_chat(self):
        other_agent = User.objects.create_user("o@example.bw", PW, role=Role.CONSULTANT)
        conv, _, _ = svc.start(self.client_user, topic="Other", first_message="Hi")
        svc.accept(conv, other_agent)
        self.client.force_login(self.agent)
        self.assertEqual(self.client.post(reverse("chat:send", args=[conv.pk]), {"body": "hi"}).status_code, 403)

    def test_reports_page(self):
        with at(TUESDAY_10AM):
            svc.set_presence(self.agent, True)
            conv, _, _ = svc.start(self.client_user, topic="Technical problem", first_message="Login issue")
            svc.accept(conv, self.agent)
            svc.close(conv, self.agent)
        self.client.force_login(self.agent)
        r = self.client.get(reverse("chat:reports"))
        self.assertContains(r, "Chats started")
        self.assertContains(r, "Topic: Technical problem")
