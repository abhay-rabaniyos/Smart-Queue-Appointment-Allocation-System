"""Pure scheduling policy, replaceable independently from persistence and HTTP."""

from typing import Protocol
from .security import utc


class QueuePolicy(Protocol):
    def order(self, tickets, at, rules): ...


class AgingPriorityPolicy:
    def order(self, tickets, at, rules):
        # Aging is unbounded so a stream of new priority arrivals cannot starve a visitor.
        def rank(ticket):
            waited = max(0, (at - utc(ticket.checked_in)).total_seconds() / 60)
            score = ticket.priority * rules.priority_weight + waited / rules.aging_minutes
            return (-score, utc(ticket.checked_in), ticket.token)

        return sorted(tickets, key=rank)
