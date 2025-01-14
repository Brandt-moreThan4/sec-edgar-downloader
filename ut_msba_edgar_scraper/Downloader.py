"""Provides a :class:`Downloader` class for downloading SEC EDGAR filings."""

from shutil import ExecError
import sys
from pathlib import Path
from typing import ClassVar, List, Optional, Union
import pandas as pd

import requests
from requests.adapters import HTTPAdapter

from ._constants import DATE_FORMAT_TOKENS, DEFAULT_AFTER_DATE, DEFAULT_BEFORE_DATE, ROOT_SAVE_FOLDER_NAME
from ._constants import SUPPORTED_FILINGS as _SUPPORTED_FILINGS
from ._utils import (download_filings, build_filings, get_number_of_unique_filings, is_cik, validate_date_format,retries)

from datetime import datetime 

from .msba_utils import get_cik_from_gvkey, get_gvkey_from_cik



TODAYS_DATE = DEFAULT_BEFORE_DATE.strftime(DATE_FORMAT_TOKENS)


class Downloader:
    """A :class:`Downloader` object.

    :param download_folder: relative or absolute path to download location.
        Defaults to the current working directory.


    """

    supported_filings: ClassVar[List[str]] = sorted(_SUPPORTED_FILINGS)

    def __init__(self, download_folder: Union[str, Path, None] = None, drive=None) -> None:
        """Constructor for the :class:`Downloader` class."""
        if download_folder is None:
            self.download_folder = Path.cwd()
        elif isinstance(download_folder, Path):
            self.download_folder = download_folder
        else:
            self.download_folder = Path(download_folder).expanduser().resolve()

        if drive is not None:
            self.drive = drive


    def get_download_folder(self):
        return self.download_folder


    def get_filings(
        self,
        filing_type: str,
        identifier: str,
        amount: Optional[int] = None,
        after: Optional[str] = None,
        before: Optional[str] = TODAYS_DATE, 
        include_amends: bool = False,
        query: str = "",
        is_gvkey=True, # Honestly, some things might break if you don't set this to True
    ) -> int:
        """ ADD DESCRIPTION HERE"""
        

        # TODAYS_DATE = DEFAULT_BEFORE_DATE.strftime(DATE_FORMAT_TOKENS)
        gvkey = None

        if is_gvkey: # If the identifier is a gvkey, then we first want to convert it to  a CIK
            gvkey = str(identifier).zfill(10)

            try: 
                identifier = get_cik_from_gvkey(identifier,date=TODAYS_DATE) # identifier is now going to be CIK
            except:
                return [] # If there is no gvkey, then return an exmpty list

        identifier = str(identifier).strip().upper()

        # Detect CIKs and ensure that they are properly zero-padded
        if is_cik(identifier):
            if len(identifier) > 10:
                raise ValueError("Invalid CIK. CIKs must be at most 10 digits long.")
            # Pad CIK with 0s to ensure that it is exactly 10 digits long
            # The SEC Edgar Search API requires zero-padded CIKs to ensure
            # that search results are accurate. Relates to issue #84.
            identifier = identifier.zfill(10)

        if amount is None:
            # If amount is not specified, obtain all available filings.
            # We simply need a large number to denote this and the loop
            # responsible for fetching the URLs will break appropriately.
            amount = sys.maxsize
        else:
            amount = int(amount)
            if amount < 1:
                raise ValueError("Invalid amount. Please enter a number greater than 1.")

        # SEC allows for filing searches from 2000 onwards
        if after is None:
            after = DEFAULT_AFTER_DATE.strftime(DATE_FORMAT_TOKENS)
        else:
            validate_date_format(after)

            if after < DEFAULT_AFTER_DATE.strftime(DATE_FORMAT_TOKENS):
                raise ValueError(
                    f"Filings cannot be downloaded prior to {DEFAULT_AFTER_DATE.year}. "
                    f"Please enter a date on or after {DEFAULT_AFTER_DATE}."
                )

        if before is None:
            before = TODAYS_DATE
        else:
            validate_date_format(before)

        if after > before:
            raise ValueError(
                "Invalid after and before date combination. "
                "Please enter an after date that is less than the before date."
            )

        if filing_type not in _SUPPORTED_FILINGS:
            filing_options = ", ".join(self.supported_filings)
            raise ValueError(
                f"'{filing}' filings are not supported. "
                f"Please choose from the following: {filing_options}."
            )

        if not isinstance(query, str):
            raise TypeError("Query must be of type string.")

        pd_before = pd.to_datetime(before)

        filings_to_fetch = build_filings(
            filing_type,
            identifier,
            amount,
            after,
            TODAYS_DATE, 
            include_amends,
            query,
        )

        if gvkey is None: # Try to get the gvkey from mapping
            try:
                gvkey = gvkey = str(get_gvkey_from_cik(filing.cik, filing.period_end_date)).zfill(10)
            except:
                pass

        for filing in filings_to_fetch:
            # I think the below line is actually bad if unless this function will only accept is_gvkey = Trues.

            filing.gvkey = gvkey # Make sure gvkey is zero padded

            filing.report_type = filing_type # Cahnge this to be what is grabbed from the hit
            filing.file_name = (f'{filing.gvkey}_{filing.period_end_date}_{filing.report_type}_{filing.accession_number}.html')
            filing.file_name_txt = (f'{filing.gvkey}_{filing.period_end_date}_{filing.report_type}_{filing.accession_number}.txt')
            filing.save_path = self.download_folder / ROOT_SAVE_FOLDER_NAME / filing.file_name
            filing.cik_lookup = identifier # This should always be the cik by the time you get here. Assuming you are using gvkey or cik lookup, not ticker.
            

        filings_to_fetch = list(filter(lambda x: x.data_date <= pd_before, filings_to_fetch))
        filings_to_fetch.sort(key=lambda x: x.data_date) # Make sure it is sorted in ascending order by period end date
            
        return filings_to_fetch


    def download_reports(
        self,
        filing_type: str,
        identifier: str,
        log_df: pd.DataFrame,
        amount: Optional[int] = None,
        after: Optional[str] = None,
        before: Optional[str] = None,
        include_amends: bool = False,
        query: str = "",
        is_gvkey=True,
        location='local',
    ):
        """ ADD DESCRIPTION HERE
        """

        filings_to_fetch = self.get_filings(filing_type,identifier,amount,after,before,include_amends,query,is_gvkey)

            
        if len(filings_to_fetch) > 0: # We do not need to call the below functions if there are no filings
            if location == 'drive':
                download_filings(filings_to_fetch, log_df,'drive', self.drive)
            elif location =='local':
                download_filings(filings_to_fetch, log_df)
            else:
                raise Exception('Bad destination.')


