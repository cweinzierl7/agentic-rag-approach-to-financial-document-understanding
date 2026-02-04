""" Query for quantitative KPIs  """


from dataclasses import dataclass, field

from typing import Optional


@dataclass
class QUANTITATIVE_KPIs_speedboat:
    client: str
    _built: bool = field(default=False, init=False)

    # Company Profile
    TOTAL_SALES_REVENUE_0: str = None
    TOTAL_SALES_REVENUE_1: str = None
    TOTAL_SALES_REVENUE_2: str = None
    GROSS_PROFIT_0: str = None
    GROSS_PROFIT_1: str = None
    GROSS_PROFIT_2: str = None
    EBITDA_0: str = None
    EBITDA_1: str = None
    EBITDA_2: str = None
    EBIT_0: str = None
    EBIT_1: str = None  
    EBIT_2: str = None  
    NET_INCOME_0: str = None
    NET_INCOME_1: str = None
    NET_INCOME_2: str = None
    TOTAL_CASH_0: str = None
    TOTAL_CASH_1: str = None
    TOTAL_CASH_2: str = None
    TOTAL_EQUITY_0: str = None
    TOTAL_EQUITY_1: str = None
    TOTAL_EQUITY_2: str = None
    TANGIBLE_NET_WORTH_0: str = None
    TANGIBLE_NET_WORTH_1: str = None
    TANGIBLE_NET_WORTH_2: str = None
    CAPEX_0: str = None
    CAPEX_1: str = None
    CAPEX_2: str = None
    FREE_CASH_FLOW_0: str = None
    FREE_CASH_FLOW_1: str = None
    FREE_CASH_FLOW_2: str = None
    UNRESTRICTED_CASH_0: str = None
    UNRESTRICTED_CASH_1: str = None
    UNRESTRICTED_CASH_2: str = None
    UNDRAWN_LOAN_FACILITIES_0: str = None
    UNDRAWN_LOAN_FACILITIES_1: str = None
    UNDRAWN_LOAN_FACILITIES_2: str = None


    def build_queries(self, year_basis: str = "fiscal year", year_0: Optional[int] = None, year_1: Optional[int] = None, year_2: Optional[int] = None):
        # year 0 is the most recent one, year 1 the one before, year 2 the one before that
        #suffix_financial_value = "Provide the financial value only."
        suffix_financial_value = ""
        if year_0 is not None:
            self.TOTAL_SALES_REVENUE_0 = f"Provide the total sales revenue for the {year_basis} {year_0} for {self.client}. The sales revenue could also be called turnover or revenue. {suffix_financial_value}"
        if year_1 is not None:
            self.TOTAL_SALES_REVENUE_1 = f"Provide the total sales revenue for the {year_basis} {year_1} for {self.client}. The sales revenue could also be called turnover or revenue. {suffix_financial_value}"
        if year_2 is not None:
            self.TOTAL_SALES_REVENUE_2 = f"Provide the total sales revenue for the {year_basis} {year_2} for {self.client}. The sales revenue could also be called turnover or revenue. {suffix_financial_value}"
        if year_0 is not None:
            self.GROSS_PROFIT_0 = f"Provide the gross profit for the {year_basis} {year_0} for {self.client}. {suffix_financial_value}"
        if year_1 is not None:
            self.GROSS_PROFIT_1 = f"Provide the gross profit for the {year_basis} {year_1} for {self.client}. {suffix_financial_value}"
        if year_2 is not None:
            self.GROSS_PROFIT_2 = f"Provide the gross profit for the {year_basis} {year_2} for {self.client}. {suffix_financial_value}"
        if year_0 is not None:
            self.EBITDA_0 = f"Provide the EBITDA (Earnings Before Interest, Taxes, Depreciation, and Amortization) for the {year_basis} {year_0} for {self.client}. {suffix_financial_value}"
        if year_1 is not None:
            self.EBITDA_1 = f"Provide the EBITDA (Earnings Before Interest, Taxes, Depreciation, and Amortization) for the {year_basis} {year_1} for {self.client}. {suffix_financial_value}"
        if year_2 is not None:
            self.EBITDA_2 = f"Provide the EBITDA (Earnings Before Interest, Taxes, Depreciation, and Amortization) for the {year_basis} {year_2} for {self.client}. {suffix_financial_value}"
        if year_0 is not None:
            self.EBIT_0 = f"Provide the EBIT (Earnings Before Interest and Taxes) for the {year_basis} {year_0} for {self.client}. {suffix_financial_value}"
        if year_1 is not None:
            self.EBIT_1 = f"Provide the EBIT (Earnings Before Interest and Taxes) for the {year_basis} {year_1} for {self.client}. {suffix_financial_value}"
        if year_2 is not None:
            self.EBIT_2 = f"Provide the EBIT (Earnings Before Interest and Taxes) for the {year_basis} {year_2} for {self.client}. {suffix_financial_value}"
        if year_0 is not None:
            self.NET_INCOME_0 = f"Provide the net income for the {year_basis} {year_0} for {self.client}. {suffix_financial_value}"
        if year_1 is not None:
            self.NET_INCOME_1 = f"Provide the net income for the {year_basis} {year_1} for {self.client}. {suffix_financial_value}"
        if year_2 is not None:
            self.NET_INCOME_2 = f"Provide the net income for the {year_basis} {year_2} for {self.client}. {suffix_financial_value}"
        if year_0 is not None:
            self.TOTAL_CASH_0 = f"Provide the total cash for the {year_basis} {year_0} for {self.client}. {suffix_financial_value}"
        if year_1 is not None:
            self.TOTAL_CASH_1 = f"Provide the total cash for the {year_basis} {year_1} for {self.client}. {suffix_financial_value}"
        if year_2 is not None:
            self.TOTAL_CASH_2 = f"Provide the total cash for the {year_basis} {year_2} for {self.client}. {suffix_financial_value}"
        if year_0 is not None:
            self.TOTAL_EQUITY_0 = f"Provide the total equity for the {year_basis} {year_0} for {self.client}. {suffix_financial_value}"
        if year_1 is not None:
            self.TOTAL_EQUITY_1 = f"Provide the total equity for the {year_basis} {year_1} for {self.client}. {suffix_financial_value}"
        if year_2 is not None:
            self.TOTAL_EQUITY_2 = f"Provide the total equity for the {year_basis} {year_2} for {self.client}. {suffix_financial_value}"
        if year_0 is not None:
            self.TANGIBLE_NET_WORTH_0 = f"Provide the tangible net worth for the {year_basis} {year_0} for {self.client}. {suffix_financial_value}"
        if year_1 is not None:
            self.TANGIBLE_NET_WORTH_1 = f"Provide the tangible net worth for the {year_basis} {year_1} for {self.client}. {suffix_financial_value}"
        if year_2 is not None:
            self.TANGIBLE_NET_WORTH_2 = f"Provide the tangible net worth for the {year_basis} {year_2} for {self.client}. {suffix_financial_value}"
        if year_0 is not None:
            self.CAPEX_0 = f"Provide the capital expenditures (Capex) for the {year_basis} {year_0} for {self.client}. {suffix_financial_value}"
        if year_1 is not None:
            self.CAPEX_1 = f"Provide the capital expenditures (Capex) for the {year_basis} {year_1} for {self.client}. {suffix_financial_value}"
        if year_2 is not None:
            self.CAPEX_2 = f"Provide the capital expenditures (Capex) for the {year_basis} {year_2} for {self.client}. {suffix_financial_value}"
        if year_0 is not None:
            self.FREE_CASH_FLOW_0 = f"Provide the free cash flow for the {year_basis} {year_0} for {self.client}. {suffix_financial_value}"
        if year_1 is not None:
            self.FREE_CASH_FLOW_1 = f"Provide the free cash flow for the {year_basis} {year_1} for {self.client}. {suffix_financial_value}"
        if year_2 is not None:
            self.FREE_CASH_FLOW_2 = f"Provide the free cash flow for the {year_basis} {year_2} for {self.client}. {suffix_financial_value}"
        if year_0 is not None:
            self.UNRESTRICTED_CASH_0 = f"Provide the unrestricted cash for the {year_basis} {year_0} for {self.client}. {suffix_financial_value}"
        if year_1 is not None:
            self.UNRESTRICTED_CASH_1 = f"Provide the unrestricted cash for the {year_basis} {year_1} for {self.client}. {suffix_financial_value}"
        if year_2 is not None:
            self.UNRESTRICTED_CASH_2 = f"Provide the unrestricted cash for the {year_basis} {year_2} for {self.client}. {suffix_financial_value}"
        if year_0 is not None:
            self.UNDRAWN_LOAN_FACILITIES_0 = f"Provide the undrawn (un-) committed loan facilities for the {year_basis} {year_0} for {self.client}. {suffix_financial_value}"
        if year_1 is not None:
            self.UNDRAWN_LOAN_FACILITIES_1 = f"Provide the undrawn (un-) committed loan facilities for the {year_basis} {year_1} for {self.client}. {suffix_financial_value}"           
        if year_2 is not None:
            self.UNDRAWN_LOAN_FACILITIES_2 = f"Provide the undrawn (un-) committed loan facilities for the {year_basis} {year_2} for {self.client}. {suffix_financial_value}"
    def all_queries(
        self,
        year_0: Optional[int],
        year_1: Optional[int] = None,
        year_2: Optional[int] = None,
        year_basis: str = "fiscal year",
    ):
        if not self._built and year_0 is not None:
            self.build_queries(year_basis=year_basis, year_0=year_0, year_1=year_1, year_2=year_2)
        elif year_0 is None:
            raise ValueError("year_0 must be provided to build queries.")
        

        return " ".join(
            value for key, value in self.__dict__.items()
            if key not in ("client", "_built") and value is not None
        )
    def all_queries_list(
        self,
        year_0: Optional[int],
        year_1: Optional[int] = None,
        year_2: Optional[int] = None,
        year_basis: str = "fiscal year",
    ):
        if not self._built and year_0 is not None:
            self.build_queries(year_basis=year_basis, year_0=year_0, year_1=year_1, year_2=year_2)
        elif year_0 is None:
            raise ValueError("year_0 must be provided to build queries.")
        

        query_list = [
            value for key, value in self.__dict__.items()
            if key not in ("client", "_built") and value is not None
        ]
        return query_list
    
    

@dataclass
class QUANTITATIVE_KPIs_consolidated:
    client: str
    _built: bool = field(default=False, init=False)

    # Company Profile
    TOTAL_SALES_REVENUE: str = None
    GROSS_PROFIT: str = None
    EBITDA: str = None
    EBIT: str = None
    NET_INCOME: str = None
    TOTAL_CASH: str = None
    TOTAL_EQUITY: str = None
    TANGIBLE_NET_WORTH: str = None
    CAPEX: str = None
    FREE_CASH_FLOW: str = None
    UNRESTRICTED_CASH: str = None
    UNDRAWN_LOAN_FACILITIES: str = None

    def build_queries(self, year_0: int, year_1: Optional[int], year_2: Optional[int]):
        # year 0 is the most recent one, year 1 the one before, year 2 the one before that
        suffix_financial_value = ""
        years = f" for the years {', '.join(str(y) for y in [year_0, year_1, year_2] if y is not None)}"
        self.TOTAL_SALES_REVENUE = f"Provide the total sales revenue{years} for {self.client}. The sales revenue could also be called turnover or revenue. {suffix_financial_value}"
        self.GROSS_PROFIT = f"Provide the gross profit{years} for {self.client}. {suffix_financial_value}"
        self.EBITDA = f"Provide the EBITDA (Earnings Before Interest, Taxes, Depreciation, and Amortization){years} for {self.client}. {suffix_financial_value}"
        self.EBIT = f"Provide the EBIT (Earnings Before Interest and Taxes){years} for {self.client}. {suffix_financial_value}"
        self.NET_INCOME = f"Provide the net income{years} for {self.client}. {suffix_financial_value}"
        self.TOTAL_CASH = f"Provide the total cash{years} for {self.client}. {suffix_financial_value}"
        self.TOTAL_EQUITY= f"Provide the total equity{years}  for {self.client}. {suffix_financial_value}"
        self.TANGIBLE_NET_WORTH= f"Provide the tangible net worth{years} for {self.client}. {suffix_financial_value}"
        self.CAPEX= f"Provide the capital expenditures (Capex){years}  for {self.client}. {suffix_financial_value}"
        self.FREE_CASH_FLOW = f"Provide the free cash flow{years} for {self.client}. {suffix_financial_value}"
        self.UNRESTRICTED_CASH= f"Provide the unrestricted cash{years} for {self.client}. {suffix_financial_value}"
        self.UNDRAWN_LOAN_FACILITIES= f"Provide the undrawn (un-) committed loan facilities{years} for {self.client}. {suffix_financial_value}"

    def all_queries(
        self,
        year_0: Optional[int],
        year_1: Optional[int] = None,
        year_2: Optional[int] = None,
        year_basis: str = "fiscal year",
    ):
        if not self._built and year_0 is not None:
            self.build_queries(year_basis=year_basis, year_0=year_0, year_1=year_1, year_2=year_2)
        elif year_0 is None:
            raise ValueError("year_0 must be provided to build queries.")
        

        return " ".join(
            value for key, value in self.__dict__.items()
            if key not in ("client", "_built") and value is not None
        )

    def all_queries_list(self, year_basis: Optional[str], year_0: Optional[int], year_1: Optional[int] = None, year_2: Optional[int] = None):

        if not self._built and year_0 is not None:
            self.build_queries(year_basis=year_basis, year_0=year_0, year_1=year_1, year_2=year_2)
        elif year_0 is None:
            raise ValueError("year_0 must be provided to build queries.")
        

        query_list = [
            value for key, value in self.__dict__.items()
            if key not in ("client", "_built") and value is not None
        ]
        return query_list
    

@dataclass
class QUANTITATIVE_KPIs_speedboat_direct:
    client: str
    _built: bool = field(default=False, init=False)

    # Company Profile
    TOTAL_SALES_REVENUE_0: str = None
    TOTAL_SALES_REVENUE_1: str = None
    TOTAL_SALES_REVENUE_2: str = None
    EBITDA_0: str = None
    EBITDA_1: str = None
    EBITDA_2: str = None
    EBIT_0: str = None
    EBIT_1: str = None  
    EBIT_2: str = None  
    NET_INCOME_0: str = None
    NET_INCOME_1: str = None
    NET_INCOME_2: str = None
    TOTAL_CASH_0: str = None
    TOTAL_CASH_1: str = None
    TOTAL_CASH_2: str = None
    TOTAL_EQUITY_0: str = None
    TOTAL_EQUITY_1: str = None
    TOTAL_EQUITY_2: str = None
    CAPEX_0: str = None
    CAPEX_1: str = None
    CAPEX_2: str = None
    FREE_CASH_FLOW_0: str = None
    FREE_CASH_FLOW_1: str = None
    FREE_CASH_FLOW_2: str = None
    UNRESTRICTED_CASH_0: str = None
    UNRESTRICTED_CASH_1: str = None
    UNRESTRICTED_CASH_2: str = None
    UNDRAWN_LOAN_FACILITIES_0: str = None
    UNDRAWN_LOAN_FACILITIES_1: str = None
    UNDRAWN_LOAN_FACILITIES_2: str = None


    def build_queries(self, year_basis: str = "fiscal year", year_0: Optional[int] = None, year_1: Optional[int] = None, year_2: Optional[int] = None):
        # year 0 is the most recent one, year 1 the one before, year 2 the one before that
        #suffix_financial_value = "Provide the financial value only."
        suffix_financial_value = ""
        if year_0 is not None:
            self.TOTAL_SALES_REVENUE_0 = f"Provide the total sales revenue for the {year_basis} {year_0} for {self.client}. The sales revenue could also be called turnover or revenue. {suffix_financial_value}"
        if year_1 is not None:
            self.TOTAL_SALES_REVENUE_1 = f"Provide the total sales revenue for the {year_basis} {year_1} for {self.client}. The sales revenue could also be called turnover or revenue. {suffix_financial_value}"
        if year_2 is not None:
            self.TOTAL_SALES_REVENUE_2 = f"Provide the total sales revenue for the {year_basis} {year_2} for {self.client}. The sales revenue could also be called turnover or revenue. {suffix_financial_value}"
        if year_0 is not None:
            self.EBITDA_0 = f"Provide the EBITDA (Earnings Before Interest, Taxes, Depreciation, and Amortization) for the {year_basis} {year_0} for {self.client}. {suffix_financial_value}"
        if year_1 is not None:
            self.EBITDA_1 = f"Provide the EBITDA (Earnings Before Interest, Taxes, Depreciation, and Amortization) for the {year_basis} {year_1} for {self.client}. {suffix_financial_value}"
        if year_2 is not None:
            self.EBITDA_2 = f"Provide the EBITDA (Earnings Before Interest, Taxes, Depreciation, and Amortization) for the {year_basis} {year_2} for {self.client}. {suffix_financial_value}"
        if year_0 is not None:
            self.EBIT_0 = f"Provide the EBIT (Earnings Before Interest and Taxes) for the {year_basis} {year_0} for {self.client}. {suffix_financial_value}"
        if year_1 is not None:
            self.EBIT_1 = f"Provide the EBIT (Earnings Before Interest and Taxes) for the {year_basis} {year_1} for {self.client}. {suffix_financial_value}"
        if year_2 is not None:
            self.EBIT_2 = f"Provide the EBIT (Earnings Before Interest and Taxes) for the {year_basis} {year_2} for {self.client}. {suffix_financial_value}"
        if year_0 is not None:
            self.NET_INCOME_0 = f"Provide the net income for the {year_basis} {year_0} for {self.client}. {suffix_financial_value}"
        if year_1 is not None:
            self.NET_INCOME_1 = f"Provide the net income for the {year_basis} {year_1} for {self.client}. {suffix_financial_value}"
        if year_2 is not None:
            self.NET_INCOME_2 = f"Provide the net income for the {year_basis} {year_2} for {self.client}. {suffix_financial_value}"
        if year_0 is not None:
            self.TOTAL_CASH_0 = f"Provide the total cash for the {year_basis} {year_0} for {self.client}. {suffix_financial_value}"
        if year_1 is not None:
            self.TOTAL_CASH_1 = f"Provide the total cash for the {year_basis} {year_1} for {self.client}. {suffix_financial_value}"
        if year_2 is not None:
            self.TOTAL_CASH_2 = f"Provide the total cash for the {year_basis} {year_2} for {self.client}. {suffix_financial_value}"
        if year_0 is not None:
            self.TOTAL_EQUITY_0 = f"Provide the total equity for the {year_basis} {year_0} for {self.client}. {suffix_financial_value}"
        if year_1 is not None:
            self.TOTAL_EQUITY_1 = f"Provide the total equity for the {year_basis} {year_1} for {self.client}. {suffix_financial_value}"
        if year_2 is not None:
            self.TOTAL_EQUITY_2 = f"Provide the total equity for the {year_basis} {year_2} for {self.client}. {suffix_financial_value}"
        if year_0 is not None:
            self.CAPEX_0 = f"Provide the capital expenditures (Capex) for the {year_basis} {year_0} for {self.client}. {suffix_financial_value}"
        if year_1 is not None:
            self.CAPEX_1 = f"Provide the capital expenditures (Capex) for the {year_basis} {year_1} for {self.client}. {suffix_financial_value}"
        if year_2 is not None:
            self.CAPEX_2 = f"Provide the capital expenditures (Capex) for the {year_basis} {year_2} for {self.client}. {suffix_financial_value}"
        if year_0 is not None:
            self.FREE_CASH_FLOW_0 = f"Provide the free cash flow for the {year_basis} {year_0} for {self.client}. {suffix_financial_value}"
        if year_1 is not None:
            self.FREE_CASH_FLOW_1 = f"Provide the free cash flow for the {year_basis} {year_1} for {self.client}. {suffix_financial_value}"
        if year_2 is not None:
            self.FREE_CASH_FLOW_2 = f"Provide the free cash flow for the {year_basis} {year_2} for {self.client}. {suffix_financial_value}"
        if year_0 is not None:
            self.UNRESTRICTED_CASH_0 = f"Provide the unrestricted cash for the {year_basis} {year_0} for {self.client}. {suffix_financial_value}"
        if year_1 is not None:
            self.UNRESTRICTED_CASH_1 = f"Provide the unrestricted cash for the {year_basis} {year_1} for {self.client}. {suffix_financial_value}"
        if year_2 is not None:
            self.UNRESTRICTED_CASH_2 = f"Provide the unrestricted cash for the {year_basis} {year_2} for {self.client}. {suffix_financial_value}"
        if year_0 is not None:
            self.UNDRAWN_LOAN_FACILITIES_0 = f"Provide the undrawn (un-) committed loan facilities for the {year_basis} {year_0} for {self.client}. {suffix_financial_value}"
        if year_1 is not None:
            self.UNDRAWN_LOAN_FACILITIES_1 = f"Provide the undrawn (un-) committed loan facilities for the {year_basis} {year_1} for {self.client}. {suffix_financial_value}"           
        if year_2 is not None:
            self.UNDRAWN_LOAN_FACILITIES_2 = f"Provide the undrawn (un-) committed loan facilities for the {year_basis} {year_2} for {self.client}. {suffix_financial_value}"
    def all_queries(self, year_basis:Optional[str],year_0: Optional[int], year_1: Optional[int] = None, year_2: Optional[int] = None):
        if not self._built and year_0 is not None:
            self.build_queries(year_basis=year_basis, year_0=year_0, year_1=year_1, year_2=year_2)
        elif year_0 is None:
            raise ValueError("year_0 must be provided to build queries.")
        

        return " ".join(
            value for key, value in self.__dict__.items()
            if key not in ("client", "_built") and value is not None
        )
    def all_queries_list(
        self,
        year_0: Optional[int],
        year_1: Optional[int] = None,
        year_2: Optional[int] = None,
        year_basis: str = "fiscal year",
    ):
        if not self._built and year_0 is not None:
            self.build_queries(year_basis=year_basis, year_0=year_0, year_1=year_1, year_2=year_2)
        elif year_0 is None:
            raise ValueError("year_0 must be provided to build queries.")
        

        query_list = [
            value for key, value in self.__dict__.items()
            if key not in ("client", "_built") and value is not None
        ]
        return query_list
    

@dataclass
class QUANTITATIVE_KPIs_speedboat_derived:
    client: str
    _built: bool = field(default=False, init=False)

    # Company Profile
    GROSS_PROFIT_0: str = None
    GROSS_PROFIT_1: str = None
    GROSS_PROFIT_2: str = None
    TANGIBLE_NET_WORTH_0: str = None
    TANGIBLE_NET_WORTH_1: str = None
    TANGIBLE_NET_WORTH_2: str = None



    def build_queries(self, year_basis: str = "fiscal year", year_0: Optional[int] = None, year_1: Optional[int] = None, year_2: Optional[int] = None):
        # year 0 is the most recent one, year 1 the one before, year 2 the one before that
        #suffix_financial_value = "Provide the financial value only."
        suffix_financial_value = ""
        if year_0 is not None:
            self.GROSS_PROFIT_0 = f"Provide the gross profit for the {year_basis} {year_0} for {self.client}. {suffix_financial_value}"
        if year_1 is not None:
            self.GROSS_PROFIT_1 = f"Provide the gross profit for the {year_basis} {year_1} for {self.client}. {suffix_financial_value}"
        if year_2 is not None:
            self.GROSS_PROFIT_2 = f"Provide the gross profit for the {year_basis} {year_2} for {self.client}. {suffix_financial_value}"
        if year_0 is not None:
            self.TANGIBLE_NET_WORTH_0 = f"Provide the tangible net worth for the {year_basis} {year_0} for {self.client}. {suffix_financial_value}"
        if year_1 is not None:
            self.TANGIBLE_NET_WORTH_1 = f"Provide the tangible net worth for the {year_basis} {year_1} for {self.client}. {suffix_financial_value}"
        if year_2 is not None:
            self.TANGIBLE_NET_WORTH_2 = f"Provide the tangible net worth for the {year_basis} {year_2} for {self.client}. {suffix_financial_value}"
    def all_queries(
        self,
        year_0: Optional[int],
        year_1: Optional[int] = None,
        year_2: Optional[int] = None,
        year_basis: str = "fiscal year",
    ):
        if not self._built and year_0 is not None:
            self.build_queries(year_basis=year_basis, year_0=year_0, year_1=year_1, year_2=year_2)
        elif year_0 is None:
            raise ValueError("year_0 must be provided to build queries.")
        

        return " ".join(
            value for key, value in self.__dict__.items()
            if key not in ("client", "_built") and value is not None
        )
    def all_queries_list(
        self,
        year_0: Optional[int],
        year_1: Optional[int] = None,
        year_2: Optional[int] = None,
        year_basis: str = "fiscal year",
    ):
        if not self._built and year_0 is not None:
            self.build_queries(year_basis=year_basis, year_0=year_0, year_1=year_1, year_2=year_2)
        elif year_0 is None:
            raise ValueError("year_0 must be provided to build queries.")
        

        query_list = [
            value for key, value in self.__dict__.items()
            if key not in ("client", "_built") and value is not None
        ]
        return query_list
    