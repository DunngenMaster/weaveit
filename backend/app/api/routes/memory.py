from fastapi import APIRouter, Query, HTTPException, status
from app.schemas.memory import (
    MemoryListResponse,
    MemoryItem,
    DeleteMemoryRequest,
    DeleteMemoryResponse
)
from app.services.weaviate_client import weaviate_client
import weaviate.classes as wvc


router = APIRouter(prefix="/v1/memory")


@router.get("", response_model=MemoryListResponse)
async def list_memories(
    user_id: str = Query(..., description="User identifier")
):
    """
    List latest 50 memories for a user.
    
    Returns memories sorted by creation date (most recent first).
    """
    
    try:
        client = weaviate_client.client
        collection = client.collections.get("MemoryItem")
        
        # Query for user's memories, excluding deleted ones
        result = collection.query.fetch_objects(
            filters=wvc.query.Filter.by_property("user_id").equal(user_id) & 
                    wvc.query.Filter.by_property("status").not_equal("deleted"),
            limit=50
        )
        
        memories = []
        for obj in result.objects:
            props = obj.properties
            created_at = props.get('created_at', '')
            if hasattr(created_at, 'isoformat'):
                created_at = created_at.isoformat()
            elif created_at:
                created_at = str(created_at)
            
            memories.append(MemoryItem(
                id=str(obj.uuid),
                kind=props.get('kind', ''),
                key=props.get('key', ''),
                text=props.get('text', ''),
                tags=props.get('tags', []),
                confidence=props.get('confidence', 0.0),
                status=props.get('status', 'active'),
                created_at=created_at
            ))
        
        # Sort by created_at descending (most recent first)
        memories.sort(key=lambda m: m.created_at, reverse=True)
        
        return MemoryListResponse(
            memories=memories,
            total=len(memories)
        )
    
    except Exception as e:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Failed to retrieve memories: {str(e)}"
        )


@router.post("/delete", response_model=DeleteMemoryResponse)
async def delete_memory(request: DeleteMemoryRequest):
    """
    Delete a memory by marking it as deleted.
    
    Soft delete - marks status as 'deleted' rather than removing from database.
    """
    
    try:
        client = weaviate_client.client
        collection = client.collections.get("MemoryItem")
        
        # First verify the memory exists and belongs to the user
        obj = collection.query.fetch_object_by_id(request.memory_id)
        
        if not obj:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail=f"Memory {request.memory_id} not found"
            )
        
        # Verify ownership
        if obj.properties.get('user_id') != request.user_id:
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail="You don't have permission to delete this memory"
            )
        
        # Soft delete by updating status
        collection.data.update(
            uuid=request.memory_id,
            properties={"status": "deleted"}
        )
        
        return DeleteMemoryResponse(
            success=True,
            message=f"Memory {request.memory_id} marked as deleted"
        )
    
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Failed to delete memory: {str(e)}"
        )
