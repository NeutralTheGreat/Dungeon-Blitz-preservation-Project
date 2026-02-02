package
{
   import flash.events.Event;
   import flash.events.IOErrorEvent;
   import flash.events.SecurityErrorEvent;
   import flash.net.Socket;
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
      
      private var socket:Socket;
      
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
         this.socket = new Socket();
         this.socket.addEventListener(Event.CONNECT,this.method_804);
         this.socket.addEventListener(IOErrorEvent.IO_ERROR,this.method_849);
         this.socket.addEventListener(SecurityErrorEvent.SECURITY_ERROR,this.method_1992);
         this.socket.addEventListener(Event.CLOSE,this.method_652);
      }
      
      private function method_652(param1:Event) : void
      {
         this.var_1203 = false;
      }
      
      private function method_849(param1:Event) : void
      {
         this.var_1203 = false;
         if(this.var_1248 != null)
         {
            this.var_1248();
         }
      }
      
      private function method_1992(param1:Event) : void
      {
         this.var_1203 = false;
         if(this.var_1248 != null)
         {
            this.var_1248();
         }
      }
      
      public function method_804(param1:Event) : void
      {
         if(this.var_1)
         {
            if(this.var_1.linkUpdater)
            {
               this.var_1.linkUpdater.method_756();
            }
            this.var_1.linkUpdater = new LinkUpdater(this.var_1);
         }
         if(this.var_1732 != null)
         {
            this.var_1732();
         }
      }
      
      public function method_403(param1:String, param2:int) : void
      {
         this.var_1203 = true;
         this.socket.connect(param1,param2);
      }
      
      public function method_353() : Boolean
      {
         return this.socket.connected;
      }
      
      public function method_205() : void
      {
         if(this.socket.connected)
         {
            this.socket.close();
         }
         this.var_1203 = false;
         this.socket.removeEventListener(Event.CONNECT,this.method_804);
         this.socket.removeEventListener(IOErrorEvent.IO_ERROR,this.method_849);
         this.socket.removeEventListener(Event.CLOSE,this.method_652);
         var_2094.push(this);
         this.var_1248 = null;
         this.var_1732 = null;
         this.socket = null;
         if(this.var_1)
         {
            this.var_1.linkUpdater = null;
            this.var_1 = null;
         }
      }
      
      public function SendPacket(param1:Packet) : void
      {
         this.socket.writeShort(param1.type);
         this.socket.writeShort(param1.var_50.method_685());
         this.socket.writeBytes(param1.var_50.var_359);
         this.socket.flush();
      }
      
      public function method_918() : Vector.<Packet>
      {
         var _loc1_:int = 0;
         var _loc2_:int = 0;
         var _loc4_:ByteArray = null;
         var _loc5_:Packet = null;
         var _loc3_:Vector.<Packet> = new Vector.<Packet>();
         while(this.socket.bytesAvailable)
         {
            if(!this.var_1535 && this.socket.bytesAvailable < PACKET_HEADER_SIZE)
            {
               break;
            }
            if(this.var_1535)
            {
               _loc1_ = this.var_1535;
               _loc2_ = this.var_2121;
               this.var_2121 = 0;
               this.var_1535 = 0;
            }
            else
            {
               _loc1_ = int(this.socket.readUnsignedShort());
               _loc2_ = int(this.socket.readUnsignedShort());
            }
            if(this.socket.bytesAvailable < _loc2_)
            {
               this.var_1535 = _loc1_;
               this.var_2121 = _loc2_;
               break;
            }
            _loc4_ = new ByteArray();
            if(_loc2_)
            {
               this.socket.readBytes(_loc4_,0,_loc2_);
            }
            _loc5_ = new Packet(_loc1_,_loc4_);
            _loc3_.push(_loc5_);
         }
         return _loc3_;
      }
      
      public function method_1935() : void
      {
      }
   }
}
