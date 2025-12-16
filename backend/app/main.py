from fastapi import FastAPI
from app.api.calendar_api import router as calender_router 
from app.api.event_extraction import router as event_extraction_router
from app.api.meet_create import router as meet_router 
from pydantic import BaseModel


class EmailRequest(BaseModel):
    email:list[str] 

app = FastAPI(
    title="Calender Agent AI ",
    version="1.0.0"
)

@app.post('/getTeamMemberEmail')
async def getTeamMemberEmail(payload:EmailRequest):
    print(payload.email)
    return{
        "status":"success",
        "status-code":"200",
        "emails":payload.email
    }



app.include_router(calender_router)
app.include_router(event_extraction_router)
app.include_router(meet_router)



@app.get("/")
async def root():
    return {"message": "Welcome to home route"}

