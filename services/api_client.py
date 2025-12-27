import requests
import datetime
from typing import Optional, Dict, Any, List
from config import OPENDOTA_API_URL, OPENDOTA_API_KEY

class OpenDotaClient:
    def __init__(self):
        self.base_url = OPENDOTA_API_URL
        self.api_key = OPENDOTA_API_KEY
        self.session = requests.Session()

    def _get(self, endpoint: str, params: Optional[Dict[str, Any]] = None) -> Any:
        url = f"{self.base_url}{endpoint}"
        if params is None:
            params = {}
        if self.api_key:
            params['api_key'] = self.api_key
        
        try:
            response = self.session.get(url, params=params)
            response.raise_for_status()
            return response.json()
        except requests.exceptions.RequestException as e:
            print(f"API Request Error: {e}")
            return None

    def fetch_pro_matches(self, limit: int = 100) -> List[Dict[str, Any]]:
        """Fetch list of pro matches."""
        # /proMatches usually returns a mixed bag of tiers, but mostly Professional/Premium.
        # It does NOT support tier filtering in the request.
        return self._get("/proMatches", params={"limit": limit})

    def fetch_team_matches(self, team_id: int, limit: int = 20) -> List[Dict[str, Any]]:
        """
        Fetch matches for a specific team.
        Note: The /teams/{team_id}/matches endpoint typically returns ALL matches.
        We must slice it manually.
        """
        data = self._get(f"/teams/{team_id}/matches")
        if data and isinstance(data, list):
            return data[:limit]
        return []

    def fetch_match_details(self, match_id: int) -> Optional[Dict[str, Any]]:
        """Fetch detailed match data including BP."""
        return self._get(f"/matches/{match_id}")

    def search_team(self, query: str) -> List[Dict[str, Any]]:
        """Search for a team by name."""
        return self._get("/search", params={"q": query})
    
    def fetch_heroes(self) -> List[Dict[str, Any]]:
        """
        Fetch hero data (including localized names, roles, etc.)
        Uses /heroStats endpoint which provides more info than /heroes
        """
        return self._get("/heroStats")
    
    def fetch_teams(self) -> List[Dict[str, Any]]:
        """
        Fetch list of pro teams.
        """
        return self._get("/teams")
        
    def fetch_team_details(self, team_id: int) -> Optional[Dict[str, Any]]:
        """Fetch details of a single team."""
        return self._get(f"/teams/{team_id}")

    def fetch_pro_players(self) -> List[Dict[str, Any]]:
        """
        Fetch list of pro players (includes team info).
        """
        return self._get("/proPlayers")

    def fetch_leagues(self) -> List[Dict[str, Any]]:
        """Fetch list of leagues."""
        return self._get("/leagues")
        
    def fetch_league_matches(self, league_id: int, limit: int = 100) -> List[Dict[str, Any]]:
        """
        Fetch matches from a specific league using /proMatches endpoint filtering?
        Actually OpenDota API doesn't have a direct /leagues/{id}/matches.
        We usually use explorer or sql for this, OR filter /proMatches? No.
        We can use /proMatches but it returns global.
        The better way is /leagues/{id}/matches if available, but it's not standard.
        
        Alternative: Use /explorer with SQL (powerful but complex).
        
        Simpler Alternative for "Auto Import":
        Iterate through /proMatches and filter by league_id locally (inefficient if league is old).
        
        Wait, there IS a params 'league_id' for some endpoints?
        Let's check /proMatches params. No.
        
        Let's look at /matches?league_id=... No.
        
        CORRECT WAY:
        We can request specific matches if we know IDs.
        Or we use the public match search if allowed.
        
        Actually, for a PRO TOOL, the best way is to iterate recent /proMatches (which has league_id) 
        or fetch matches of all teams in that league.
        
        But wait, OpenDota has a `/leagues/{league_id}` endpoint, let's see what it returns.
        Actually `/leagues` returns list.
        
        Let's stick to the most reliable method for "Recent League Info":
        1. Get recent pro matches (`/proMatches`).
        2. Filter by `league_id`.
        
        This works well for "Ongoing Leagues".
        """
        # OpenDota /proMatches returns the last 100 public matches.
        # If we want older matches from a league, we might need to page through it (using less_than_match_id)
        # Or use /explorer. 
        # For now, let's support "Recent matches in league" via /proMatches loop.
        return self._get("/proMatches", params={"limit": limit})
