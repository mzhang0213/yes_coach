from abc import abstractmethod, ABC
from dataclasses import dataclass
from typing import Any, Literal, Generic, TypeVar

T=TypeVar("T")
class Checkpoint(ABC, Generic[T]):
    title:str
    indicator:T

    @abstractmethod
    def reached(self, state: T)->bool:
        pass

'''
design notes
-this will b fed into agent context right
-we prob care that 
-https://static.developer.riotgames.com/docs/lol/liveclientdata_events.json
examples
Checkpoint(15 min ff, game clock == 15)
Checkpoint(first baron spawn, game clock == 20)
Checkpoint(elder spawn, game clock == x mins after last drag)
Checkpoint(first inhib, when the inhib dies [type Riot API InhibKilled])
'''