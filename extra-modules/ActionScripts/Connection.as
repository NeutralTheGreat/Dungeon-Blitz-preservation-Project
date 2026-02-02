package
{
   import flash.utils.ByteArray;
   
   public class Connection
   {
      
      private static var var_2094:Vector.<Connection> = new Vector.<Connection>();
      
      private static var TYPE_ITERATOR:uint = 1;
      
      public static const const_1340:uint = TYPE_ITERATOR++;
      
      public static const const_1361:uint = TYPE_ITERATOR++;
      
      public static const const_1386:uint = TYPE_ITERATOR++;
      
      public static const const_1405:uint = TYPE_ITERATOR++;
      
      public static const const_1359:uint = TYPE_ITERATOR++;
      
      public static const const_1408:uint = TYPE_ITERATOR++;
      
      public static const const_1342:uint = TYPE_ITERATOR++;
      
      public static const const_868:uint = TYPE_ITERATOR;
      
      public static const PACKET_HEADER_SIZE:uint = 4;
      
      public static const LOGINSERVER_PORT:uint = 443;
       
      
      internal var var_1:Game;
      
      private var transport:IConnectionTransport;
      
      internal var var_1203:Boolean;
      
      internal var var_1535:int;
      
      internal var var_3002:uint;
      
      internal var var_2121:int;
      
      internal var var_1248:Function;
      
      internal var var_1732:Function;
      
      public function Connection(param1:Game, param2:Function = null, param3:Function = null)
      {
         super();
         this.var_1 = param1;
         this.var_1248 = param3;
         this.var_1732 = param2;
         this.transport = new WebSocketTransport();
         this.transport.onConnect = this.onTransportConnect;
         this.transport.onClose = this.onTransportClose;
         this.transport.onError = this.onTransportError;
      }
      
      private function onTransportClose():void
      {
         this.var_1203 = false;
      }
      
      private function onTransportError():void
      {
         this.var_1203 = false;
         if (this.var_1248 != null)
         {
            this.var_1248();
         }
      }
      
      private function onTransportConnect():void
      {
         if (this.var_1)
         {
            if (this.var_1.linkUpdater)
            {
               this.var_1.linkUpdater.method_756();
            }
            this.var_1.linkUpdater = new LinkUpdater(this.var_1);
         }
         if (this.var_1732 != null)
         {
            this.var_1732();
         }
      }
      
      public function method_804(param1:* = null):void
      {
         this.onTransportConnect();
      }
      
      public function method_403(param1:String, param2:int):void
      {
         this.var_1203 = true;
         this.transport.connect(param1, param2);
      }
      
      public function method_353():Boolean
      {
         return this.transport.connected;
      }
      
      public function method_205():void
      {
         if (this.transport.connected)
         {
            this.transport.close();
         }
         this.var_1203 = false;
         var_2094.push(this);
         this.var_1248 = null;
         this.var_1732 = null;
         this.transport = null;
         
         if (this.var_1)
         {
            this.var_1.linkUpdater = null;
            this.var_1 = null;
         }
      }
      
      public function SendPacket(param1:Packet):void
      {
         var packetData:ByteArray = new ByteArray();
         packetData.writeShort(param1.type);
         packetData.writeShort(param1.var_50.method_685());
         packetData.writeBytes(param1.var_50.var_359);
         this.transport.writeBytes(packetData);
         this.transport.flush();
      }
      
      public function method_918():Vector.<Packet>
      {
         var _loc1_:int = 0;
         var _loc2_:int = 0;
         var _loc4_:ByteArray = null;
         var _loc5_:Packet = null;
         var headerBuffer:ByteArray = null;
         var _loc3_:Vector.<Packet> = new Vector.<Packet>();
         
         while (this.transport.bytesAvailable)
         {
            if (!this.var_1535 && this.transport.bytesAvailable < PACKET_HEADER_SIZE)
            {
               break;
            }
            
            if (this.var_1535)
            {
               _loc1_ = this.var_1535;
               _loc2_ = this.var_2121;
               this.var_2121 = 0;
               this.var_1535 = 0;
            }
            else
            {
               headerBuffer = new ByteArray();
               this.transport.readBytes(headerBuffer, 0, PACKET_HEADER_SIZE);
               headerBuffer.position = 0;
               _loc1_ = int(headerBuffer.readUnsignedShort());
               _loc2_ = int(headerBuffer.readUnsignedShort());
            }
            
            if (this.transport.bytesAvailable < _loc2_)
            {
               this.var_1535 = _loc1_;
               this.var_2121 = _loc2_;
               break;
            }
            
            _loc4_ = new ByteArray();
            if (_loc2_)
            {
               this.transport.readBytes(_loc4_, 0, _loc2_);
            }
            
            _loc5_ = new Packet(_loc1_, _loc4_);
            _loc3_.push(_loc5_);
         }
         
         return _loc3_;
      }
      
      public function method_1935():void
      {
      }
   }
}
