from abc import ABC,abstractmethod
from datetime import datetime
from pydantic import  BaseModel

class BusySlot(BaseModel):
    start: datetime
    end:datetime

class MeetingDetails(BaseModel):
    event_id:str 
    join_url:str 
    start: datetime
    end: datetime


class CalendarProvider(ABC):

    @abstractmethod
    def get_availability(self,user_ids:list[str],date: datetime)-> dict[str, list[BusySlot]]:
        ...

    @abstractmethod
    def create_meeting(self,
                        organizer_id: str,
                        attendee_ids: list[str],
                        start: datetime,
                        end: datetime,
                        title: str,
                        )->MeetingDetails:
        ...
        
    


