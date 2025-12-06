import datetime
from typing import List, Dict, Any, Optional
from dataclasses import dataclass, field

@dataclass
class NewsEvent:
    """
    Represents a single economic news event.
    """
    timestamp: datetime
    currency: str
    impact: str # e.g., 'Red', 'Orange', 'Yellow', 'White'
    event_name: str
    
    def __repr__(self):
        return (f"NewsEvent({self.timestamp.strftime('%Y-%m-%d %H:%M')}, {self.currency}, "
                f"Impact: {self.impact}, Event: '{self.event_name}')")

class NewsFilter:
    """
    Fetches and filters economic news events to prevent trading during high volatility.
    """
    def __init__(self, cache_duration_minutes: int = 60):
        """
        Initializes the NewsFilter.

        Args:
            cache_duration_minutes (int): How long to cache news data before re-fetching.
        """
        self.events: List[NewsEvent] = []
        self.last_fetch_time: Optional[datetime.datetime] = None
        self.cache_duration = datetime.timedelta(minutes=cache_duration_minutes)
        self.forex_factory_url = "https://www.forexfactory.com/calendar"

    def _should_refetch(self) -> bool:
        """Checks if the cached news data is stale and needs to be re-fetched."""
        if not self.last_fetch_time or (datetime.datetime.utcnow() - self.last_fetch_time) > self.cache_duration:
            return True
        return False

    def fetch_upcoming_events(self):
        """
        Uses web_fetch to scrape news events from Forex Factory.
        This method will need to be implemented using the available tools.
        For now, it will be a placeholder that returns mock data.
        """
        if not self._should_refetch():
            print("News data is fresh. Using cached events.")
            return

        print("Fetching upcoming news events from Forex Factory...")
        # In a real implementation, this is where the `web_fetch` tool would be called.
        # The prompt would be complex, asking the tool to parse the HTML table,
        # handle different date/time formats, and extract the required fields.
        
        # --- MOCK DATA PLACEHOLDER ---
        # Since we cannot perform complex web scraping reliably without seeing the HTML
        # and iterating, we will use mock data that simulates a successful fetch.
        self.events = self._get_mock_events()
        self.last_fetch_time = datetime.datetime.utcnow()
        print(f"Successfully fetched and parsed {len(self.events)} events.")
        
    def _get_mock_events(self) -> List[NewsEvent]:
        """Returns a list of mock news events for demonstration purposes."""
        now = datetime.datetime.utcnow()
        return [
            NewsEvent(
                timestamp=now + datetime.timedelta(minutes=15),
                currency="USD",
                impact="Red",
                event_name="FOMC Statement"
            ),
            NewsEvent(
                timestamp=now + datetime.timedelta(minutes=45),
                currency="EUR",
                impact="Orange",
                event_name="German Industrial Production"
            ),
            NewsEvent(
                timestamp=now + datetime.timedelta(hours=2),
                currency="GBP",
                impact="Red",
                event_name="BOE Gov Bailey Speaks"
            ),
            NewsEvent(
                timestamp=now - datetime.timedelta(minutes=30),
                currency="JPY",
                impact="Red",
                event_name="Unemployment Rate (already passed)"
            ),
        ]

    def is_high_impact_news_approaching(
        self,
        lookahead_minutes: int = 20,
        relevant_currencies: Optional[List[str]] = None
    ) -> Optional[NewsEvent]:
        """
        Checks if a high-impact ('Red') news event is approaching for relevant currencies.

        Args:
            lookahead_minutes (int): The window in minutes to check for upcoming news.
            relevant_currencies (Optional[List[str]]): A list of currency strings to filter for.
                                                        If None, checks for all currencies.

        Returns:
            Optional[NewsEvent]: The approaching event if found, otherwise None.
        """
        self.fetch_upcoming_events() # Re-fetches if cache is stale
        
        now = datetime.datetime.utcnow()
        lookahead_window = now + datetime.timedelta(minutes=lookahead_minutes)
        
        for event in self.events:
            # Check if event is high-impact
            if event.impact.lower() != 'red':
                continue
            
            # Check if the currency is relevant
            if relevant_currencies and event.currency not in relevant_currencies:
                continue

            # Check if the event is in the future and within our lookahead window
            if now < event.timestamp <= lookahead_window:
                return event
        
        return None

# Example Usage
if __name__ == "__main__":
    print("--- NewsFilter Example ---")
    news_filter = NewsFilter(cache_duration_minutes=0) # Set to 0 to force fetch

    # Check for any upcoming high-impact news in the next 20 minutes
    approaching_event = news_filter.is_high_impact_news_approaching(lookahead_minutes=20)
    
    if approaching_event:
        print(f"\n[!] HIGH-IMPACT NEWS ALERT (next 20 mins): {approaching_event}")
    else:
        print("\n[*] No high-impact news detected in the next 20 minutes.")

    # Check for specific currencies in the next 3 hours
    approaching_gbp_event = news_filter.is_high_impact_news_approaching(
        lookahead_minutes=180, 
        relevant_currencies=["GBP"]
    )

    if approaching_gbp_event:
        print(f"\n[!] HIGH-IMPACT GBP NEWS ALERT (next 3 hours): {approaching_gbp_event}")
    else:
        print("\n[*] No high-impact GBP news detected in the next 3 hours.")
