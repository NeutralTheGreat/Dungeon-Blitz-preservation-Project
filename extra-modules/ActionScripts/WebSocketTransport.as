package
{
   import flash.utils.ByteArray;
   import flash.utils.getDefinitionByName;
   
   public class WebSocketTransport implements IConnectionTransport
   {
      private var _useSecure:Boolean = false;
      
      private var _websocket:* = null;
      
      private var _connected:Boolean = false;
      
      private var _receiveBuffer:ByteArray;
      
      private var _onConnect:Function = null;
      private var _onClose:Function = null;
      private var _onError:Function = null;
      
      public function WebSocketTransport(useSecure:Boolean = false)
      {
         _useSecure = useSecure;
         _receiveBuffer = new ByteArray();
      }
      
      public function connect(host:String, port:int):void
      {
         var protocol:String = _useSecure ? "wss" : "ws";
         var url:String = protocol + "://" + host + ":" + port;
         
         try
         {
            var WebSocketClass:Class = getDefinitionByName("flash.net.WebSocket") as Class;
            
            if (WebSocketClass != null)
            {
               _websocket = new WebSocketClass(url);
               _websocket.binaryType = "arraybuffer";
               _websocket.addEventListener("open", handleOpen);
               _websocket.addEventListener("close", handleClose);
               _websocket.addEventListener("error", handleError);
               _websocket.addEventListener("message", handleMessage);
            }
            else
            {
               if (_onError != null)
               {
                  _onError();
               }
            }
         }
         catch (e:Error)
         {
            if (_onError != null)
            {
               _onError();
            }
         }
      }
      
      private function handleOpen(event:*):void
      {
         _connected = true;
         
         if (_onConnect != null)
         {
            _onConnect();
         }
      }
      
      private function handleClose(event:*):void
      {
         _connected = false;
         
         if (_onClose != null)
         {
            _onClose();
         }
      }
      
      private function handleError(event:*):void
      {
         _connected = false;
         
         if (_onError != null)
         {
            _onError();
         }
      }
      
      private function handleMessage(event:*):void
      {
         var data:ByteArray = event.data as ByteArray;
         
         if (data != null)
         {
            var currentPosition:uint = _receiveBuffer.position;
            _receiveBuffer.position = _receiveBuffer.length;
            _receiveBuffer.writeBytes(data);
            _receiveBuffer.position = currentPosition;
         }
      }
      
      public function get connected():Boolean
      {
         return _connected;
      }
      
      public function writeBytes(data:ByteArray):void
      {
         if (_websocket != null && _connected)
         {
            data.position = 0;
            _websocket.send(data);
         }
      }
      
      public function flush():void
      {
      }
      
      public function readBytes(target:ByteArray, offset:uint, length:uint):void
      {
         if (_receiveBuffer.bytesAvailable >= length)
         {
            _receiveBuffer.readBytes(target, offset, length);
            compactBuffer();
         }
      }
      
      public function get bytesAvailable():uint
      {
         return _receiveBuffer.bytesAvailable;
      }
      
      public function close():void
      {
         if (_websocket != null)
         {
            try
            {
               _websocket.removeEventListener("open", handleOpen);
               _websocket.removeEventListener("close", handleClose);
               _websocket.removeEventListener("error", handleError);
               _websocket.removeEventListener("message", handleMessage);
               
               _websocket.close();
            }
            catch (e:Error)
            {
            }
            
            _websocket = null;
         }
         
         _connected = false;
         _receiveBuffer = new ByteArray();
      }
      
      public function set onConnect(callback:Function):void
      {
         _onConnect = callback;
      }
      
      public function set onClose(callback:Function):void
      {
         _onClose = callback;
      }
      
      public function set onError(callback:Function):void
      {
         _onError = callback;
      }
      
      private function compactBuffer():void
      {
         if (_receiveBuffer.position > 0)
         {
            var remaining:ByteArray = new ByteArray();
            
            if (_receiveBuffer.bytesAvailable > 0)
            {
               _receiveBuffer.readBytes(remaining);
            }
            
            _receiveBuffer = remaining;
         }
      }
   }
}
