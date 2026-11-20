import logging
from typing import Optional, List, Dict, Any
from fastapi import APIRouter, Depends, HTTPException, Body, status
from pydantic import BaseModel

from Backend.api.auth_middleware import get_current_user_required
from Backend.services.supabase_service import (
    create_conversation,
    get_user_conversations,
    rename_conversation,
    delete_conversation,
    get_conversation_messages,
    verify_conversation_ownership
)

router = APIRouter()
logger = logging.getLogger("uvicorn.error")


class CreateConversationRequest(BaseModel):
    title: Optional[str] = "New Conversation"


class RenameConversationRequest(BaseModel):
    title: str


@router.get("/conversations")
def list_conversations(user: Dict[str, Any] = Depends(get_current_user_required)):
    """List all private conversations strictly belonging to the authenticated user."""
    user_id = user["id"]
    convs = get_user_conversations(user_id)
    return {
        "success": True,
        "user_id": user_id,
        "conversations": convs
    }


@router.post("/conversations")
def new_conversation(
    payload: CreateConversationRequest = Body(default=CreateConversationRequest()),
    user: Dict[str, Any] = Depends(get_current_user_required)
):
    """Create a new private conversation for the authenticated user."""
    user_id = user["id"]
    try:
        conv = create_conversation(user_id=user_id, title=payload.title or "New Conversation")
        return {
            "success": True,
            "conversation": conv
        }
    except Exception as e:
        logger.error(f"Error creating conversation: {e}")
        raise HTTPException(status_code=500, detail="Failed to create conversation.")


@router.get("/conversations/{conversation_id}/messages")
def get_messages(
    conversation_id: str,
    user: Dict[str, Any] = Depends(get_current_user_required)
):
    """
    Retrieve chronologically ordered messages for a conversation.
    Strictly verifies conversation ownership to prevent User A accessing User B's history.
    """
    user_id = user["id"]
    if not verify_conversation_ownership(user_id=user_id, conversation_id=conversation_id):
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Access denied. You do not have permission to view this conversation."
        )

    messages = get_conversation_messages(user_id=user_id, conversation_id=conversation_id)
    return {
        "success": True,
        "conversation_id": conversation_id,
        "messages": messages
    }


@router.patch("/conversations/{conversation_id}")
def update_conversation(
    conversation_id: str,
    payload: RenameConversationRequest,
    user: Dict[str, Any] = Depends(get_current_user_required)
):
    """Rename a conversation owned by the authenticated user."""
    user_id = user["id"]
    if not verify_conversation_ownership(user_id=user_id, conversation_id=conversation_id):
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Access denied. You do not have permission to modify this conversation."
        )

    success = rename_conversation(user_id=user_id, conversation_id=conversation_id, new_title=payload.title)
    if not success:
        raise HTTPException(status_code=404, detail="Conversation not found or could not be updated.")

    return {
        "success": True,
        "conversation_id": conversation_id,
        "title": payload.title
    }


@router.delete("/conversations/{conversation_id}")
def remove_conversation(
    conversation_id: str,
    user: Dict[str, Any] = Depends(get_current_user_required)
):
    """Delete a conversation and its messages owned by the authenticated user."""
    user_id = user["id"]
    if not verify_conversation_ownership(user_id=user_id, conversation_id=conversation_id):
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Access denied. You do not have permission to delete this conversation."
        )

    success = delete_conversation(user_id=user_id, conversation_id=conversation_id)
    if not success:
        raise HTTPException(status_code=404, detail="Conversation not found or could not be deleted.")

    return {
        "success": True,
        "conversation_id": conversation_id
    }
