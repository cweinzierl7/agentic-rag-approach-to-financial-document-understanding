""" Query for qualitative KPIs  """


from dataclasses import dataclass, field
from typing import Optional


@dataclass
class QualitativeKPIs_simple:
    client: str
    _built: bool = field(default=False, init=False)

    # Company Profile
    COMPANY_NAME: str = None
    OWNERSHIP: str = None
    MARKET_CAP: str = None
    OWNERSHIP_STRUCTURE: str = None
    MANAGEMENT: str = None
    HEADQUARTER: str = None
    INDUSTRY: str = None
    SECTOR: str = None
    EMPLOYEES: str = None
    EXTERNAL_RATING: str = None

    # Industry and Market
    INDUSTRY_TREND: str = None
    CYCLICALITY: str = None
    COMPETITORS: str = None
    PEER_GROUP: str = None
    REGULATORY_ECONOMIC_FACTORS: str = None

    # Business Model
    HISTORICAL_BACKGROUND: str = None
    MA_HISTORY: str = None
    GEOGRAPHICAL_PRESENCE: str = None
    BUSINESS_SEGMENTS: str = None
    PRODUCT_SERVICES: str = None
    VALUE_CHAIN: str = None
    KEY_SUPPLIERS: str = None
    TOP_CLIENTS: str = None
    RISKS_MITIGATION: str = None
    SWOT_ANALYSIS: str = None

    def build_queries(self):
        self.COMPANY_NAME = f"What is the Company Name of {self.client}?"
        self.OWNERSHIP = f"Is the Ownership of {self.client} public or private?"
        self.MARKET_CAP = f"What is the most recent Market cap of {self.client}?"
        self.OWNERSHIP_STRUCTURE = f"What is the Ownership structure in % of {self.client}?"
        self.MANAGEMENT = f"Who is in Management of {self.client}?"
        self.HEADQUARTER = f"Where is the Headquarter (country) of {self.client}?"
        self.INDUSTRY = f"What is the Industry of {self.client}?"
        self.SECTOR = f"What is the Sector of {self.client}?"
        self.EMPLOYEES = f"How many employees are there in {self.client}?"
        self.EXTERNAL_RATING = f"What is the external rating of {self.client}?"
        self.INDUSTRY_TREND = f"What are the current trends in the industry of {self.client}?"
        self.CYCLICALITY = f"Is the industry of {self.client} cyclical or non-cyclical?"
        self.COMPETITORS = f"What is the competitive landscape and market position of {self.client}?"
        self.PEER_GROUP = f"Who are the main competitors in the peer group of {self.client}?"
        self.REGULATORY_ECONOMIC_FACTORS = f"What are the key regulatory and economic factors impacting {self.client}?"
        self.HISTORICAL_BACKGROUND = f"What is the historical background and major company milestones of {self.client}?"
        self.MA_HISTORY = f"What is the M&A history of {self.client}?"
        self.GEOGRAPHICAL_PRESENCE = f"What is the geographical presence and market reach of {self.client}?"
        self.BUSINESS_SEGMENTS = f"What are the main business segments and revenue streams of {self.client}?"
        self.PRODUCT_SERVICES = f"What are the key products and services offered by {self.client}?"
        self.VALUE_CHAIN = f"What is the value chain and supply chain dynamics of {self.client}?"
        self.KEY_SUPPLIERS = f"Who are the key suppliers and partners of {self.client}?"
        self.TOP_CLIENTS = f"Who are the top 10 clients and customer base of {self.client}?"
        self.RISKS_MITIGATION = f"What are the major risks and mitigation strategies of {self.client}?"
        self.SWOT_ANALYSIS = f"What is the SWOT analysis of {self.client}?"

        self._built = True  # mark as built

    def all_queries(self):
        if not self._built:
            self.build_queries()

        return " ".join(
            value for key, value in self.__dict__.items()
            if key not in ("client", "_built") and value is not None
        )



@dataclass
class QualitativeKPIs_speedboat:
    client: str
    _built: bool = field(default=False, init=False)

    # Company Profile
    COMPANY_NAME: str = None
    OWNERSHIP: str = None
    MARKET_CAP: str = None
    OWNERSHIP_STRUCTURE: str = None
    MANAGEMENT: str = None
    HEADQUARTER: str = None
    INDUSTRY: str = None
    SECTOR: str = None
    EMPLOYEES: str = None
    EXTERNAL_RATING: str = None

    # Industry and Market
    INDUSTRY_TREND: str = None
    CYCLICALITY: str = None
    COMPETITORS: str = None
    PEER_GROUP: str = None
    REGULATORY_ECONOMIC_FACTORS: str = None

    # Business Model
    HISTORICAL_BACKGROUND: str = None
    MA_HISTORY: str = None
    GEOGRAPHICAL_PRESENCE: str = None
    BUSINESS_SEGMENTS: str = None
    PRODUCT_SERVICES: str = None
    VALUE_CHAIN: str = None
    KEY_SUPPLIERS: str = None
    TOP_CLIENTS: str = None
    RISKS_MITIGATION: str = None
    SWOT_ANALYSIS: str = None

    def build_queries(self):
        self.COMPANY_NAME = f"Assume a role of a credit risk underwriter. What is the full name of the {self.client} company (group) that is being the focus of the documents. Often the company name is derived from the borrower name and the sponsors behind. If you are not sure, give all the variants.?"
        self.OWNERSHIP = f"Does {self.client} have public or private ownership? Is it listed on public stock exchange? Please provide ownership share in %"
        self.MARKET_CAP = f"What is the market capitalisation of {self.client}? Specify the date. If no Market capitalisation can be found answer with n/a"
        self.OWNERSHIP_STRUCTURE = f"What is the ownership structure of the {self.client} (or borrower) in %?"
        self.MANAGEMENT = f"Who is in the management team of {self.client} (CEO, board)?"
        self.HEADQUARTER = f"In what city and country are the headquarters of {self.client} situated today, latest info?"
        self.INDUSTRY = f"What is the industry or field of operations of {self.client}? Provide NACE code if available."
        self.SECTOR = f"What is the industry sector of {self.client}?"
        self.EMPLOYEES = f"What is number of employees of the {self.client} company / group? If not stated, state n/a.?"
        self.EXTERNAL_RATING = f"What is the external rating and rating outlook of {self.client}? (name the agency in brackets)"
        self.INDUSTRY_TREND = f"What are the main characteristics of the industry {self.client} is in, what are the industry trends and growth projects. What are challenges that the industry faces?"
        self.CYCLICALITY = f"Is the market {self.client} operates in cyclical? If no clear evidence, give indication where the market might be. If yes, explain in which point of the cycle are we."
        self.COMPETITORS = f"What are the key competitors and peers for each of the segment of the business of {self.client}?"
        self.PEER_GROUP = f"How does the {self.client} company / group compares to its peers? Is there a unique selling point (USP)? Give a detailed description in bullet points."
        self.REGULATORY_ECONOMIC_FACTORS = f"What are the key regulatory and economic risk factors affecting the industry {self.client} is in?"
        self.HISTORICAL_BACKGROUND = f"What are the major company milestones of {self.client}? Please provide a list in chronological order"
        self.MA_HISTORY = f"Does {self.client} has a merger and / or acquistion history or strategy? What is the companies M&A history? Please provide a list of M&A events in chronological order"
        self.GEOGRAPHICAL_PRESENCE = f"In what geographical regions is {self.client} present? What are the regions with the best sales? Provide sales breakdown by segment if available?"
        self.BUSINESS_SEGMENTS = f"How do business segments and services of {self.client} break down geographically?"
        self.PRODUCT_SERVICES = f"What are the products / services which the {self.client} company / group provide? How do products and services break down geographically?"
        self.VALUE_CHAIN = f"Describe the value chain for {self.client}"
        self.KEY_SUPPLIERS = f"What are the suppliers for the business model of {self.client} company / group which are required for delivering their services?"
        self.TOP_CLIENTS = f"What are the top 10 clients of {self.client} by revenue generated?"
        self.RISKS_MITIGATION = f"You are a credit risk underwriter and you are reviewing the {self.client} case. What are the key risks for the business and what are the mitigants?"
        self.SWOT_ANALYSIS = f"Provide the Strengths, Weaknesses, Opportunities, and Threats analysis for {self.client} based on for example the business model, the competetive situation and peers"

        self._built = True  # mark as built

    def all_queries(self):
        if not self._built:
            self.build_queries()

        return " ".join(
            value for key, value in self.__dict__.items()
            if key not in ("client", "_built") and value is not None
        )
    
    def all_queries_list(self):
        if not self._built:
            self.build_queries()

        query_list = [
            value for key, value in self.__dict__.items()
            if key not in ("client", "_built") and value is not None
        ]
        return query_list