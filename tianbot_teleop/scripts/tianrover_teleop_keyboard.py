#!/usr/bin/env python

import threading
import rospy

from std_msgs.msg import String                     # motion_mode msgs type
from geometry_msgs.msg import Twist                 # cmd_vel msgs type  (rotate and onmi)
from geometry_msgs.msg import TwistStamped
from ackermann_msgs.msg import AckermannDrive       # cmd_vel msgs type (ackermann)
from ackermann_msgs.msg import AckermannDriveStamped

import sys
from select import select                           # 'module' object is not callable

if sys.platform == 'win32':
    import msvcrt
else:
    import termios
    import tty

msg = """
Reading from the keyboard  and Publishing to Ackermann or Twist!
---------------------------
Motion mode:
   a: ackermann mode
   s: rotate mode
   z: onmi mode

---------------------------
Moving around:
   u    i    o
   j    k    l
   m    ,    .

For Holonomic mode (strafing), hold down the shift key:
---------------------------
   U    I    O
   J    K    L
   M    <    >

t : up (+z)
b : down (-z)

anything else : stop

q/z : increase/decrease max speeds by 10%
w/x : increase/decrease only linear speed by 10%
e/c : increase/decrease only angular speed by 10%

CTRL-C to quit
"""

modeBindings = {
        'a':"ackermann",
        's':"rotate",
        'z':"omni",
}

moveBindings = {
        'i':(1,0,0,0),
        'o':(1,0,0,-1),
        'j':(0,0,0,1),
        'l':(0,0,0,-1),
        'u':(1,0,0,1),
        ',':(-1,0,0,0),
        '.':(-1,0,0,1),
        'm':(-1,0,0,-1),
        'O':(1,-1,0,0),
        'I':(1,0,0,0),
        'J':(0,1,0,0),
        'L':(0,-1,0,0),
        'U':(1,1,0,0),
        '<':(-1,0,0,0),
        '>':(-1,-1,0,0),
        'M':(-1,1,0,0),
        't':(0,0,1,0),
        'b':(0,0,-1,0),
    }

speedBindings={
        'q':(1.1,1.1),
        'z':(.9,.9),
        'w':(1.1,1),
        'x':(.9,1),
        'e':(1,1.1),
        'c':(1,.9),
    }

class PublishThread(threading.Thread):
    def __init__(self,rate):
        super(PublishThread, self).__init__()
        self.publisher = rospy.Publisher('ackermann_cmd', AckermannDriveStamped, queue_size = 1)
        self.motion_mode_publisher = rospy.Publisher('motion_mode', String, queue_size = 10)
        self.speed = 0.0
        self.turn = 0.0
        self.motion_mode = "ackermann"
        self.condition = threading.Condition()
        self.done = False

        # Set timeout to None if rate is 0 (causes new_message to wait forever
        # for new data to publish)
        if rate != 0.0:
            self.timeout = 1.0 / rate
        else:
            self.timeout = None

        self.start()

    def wait_for_subscribers(self): 
        i = 0
        while not rospy.is_shutdown() and self.publisher.get_num_connections() == 0:
            if i == 4:
                print("waiting for subscriber to connect to {}".format(self.publisher.name))
            rospy.sleep(0.5)
            i += 1
            i = i % 5
        if rospy.is_shutdown():
            raise Exception("Got shutdown request before subscribers connected")

    def update(self, turn, speed, motion_mode):
        self.condition.acquire()

        # topic 
        self.steering_angle  = turn
        self.steering_angle_velocity = 1.0
        self.speed = speed
        self.acceleration= 1.0
        self.jerk = 0.5

        # topic motion_mode  ackmann rotate omni
        self.motion_mode = motion_mode

        # Notify publish thread that we have a new message.
        self.condition.notify()
        self.condition.release()
         
    def stop(self):
        self.done = True
        self.update(0, 0, "ackermann")
        self.join()

    def run(self):
        # ackmann rotate omni

        ackerman_msg = AckermannDriveStamped()
        motion_mode_msg = String()

        if stamped:
            ackerman = AckermannDriveStamped()
            ackerman_msg.header.stamp = rospy.Time.now()
            ackerman_msg.header.frame_id = cmd_frame
        else:
            ackerman = ackerman_msg
        while not self.done:
            if stamped:
                ackerman_msg.header.stamp = rospy.Time.now()
            self.condition.acquire()
            
            # wait for a new message ot timeout
            self.condition.wait(self.timeout)
            # Copy state into twist message
            # motion_moode "ackermann" | "rotate"  | "omni"

            ackerman.drive.speed = speed
            ackerman.drive.acceleration = 0
            ackerman.drive.jerk = 0
            ackerman.drive.steering_angle = turn
            ackerman.drive.steering_angle_velocity = 0
            motion_mode_msg.data = motion_mode

            self.condition.release()

            # publish
            self.publisher.publish(ackerman)
            self.motion_mode_publisher.publish(motion_mode_msg)

        # Publish stop message when thread exits.
        ackerman.drive.speed = 0
        ackerman.drive.acceleration = 0
        ackerman.drive.jerk = 0
        ackerman.drive.steering_angle = 0
        ackerman.drive.steering_angle_velocity = 0


        self.publisher.publish(ackerman_msg)
        self.motion_mode_publisher.publish(motion_mode_msg)

def motion_mode_switch(key):                                     # switch motion_mode
    motion_mode = modeBindings[key]       # MOVE_TYPE_ACKERMAN
    
    # ROS_INFO motion_mode
    if (key == 'a'):                # MOVE_TYPE_ACKERMAN
        rospy.loginfo("rover motion mode set to ackermann")
    elif (key == 's'):              # MOVE_TYPE_ROTATE   
        rospy.loginfo("rover motion mode set to rotate")  
    elif (key == 'z'):     # MOVE_TYPE_OMNI 
        rospy.loginfo("rover motion mode set to omni")
    else:
        rospy.loginfo("tianrover motion mode set failed, only ackermann / rotate / omni supported!")

    rospy.loginfo('Publishing: "%s"' % motion_mode)     # print log, indicate the mode switching 
    return motion_mode

def getKey(settings, timeout):
    if sys.platform == 'win32':
        # getwch() returns a string on Windows
        key = msvcrt.getwch()
    else:
        tty.setraw(sys.stdin.fileno())
        # sys.stdin.read() returns a string on Linux
        rlist, _, _ = select([sys.stdin], [], [], timeout)
        if rlist:
            key = sys.stdin.read(1)
        else:
            key = ''
        termios.tcsetattr(sys.stdin, termios.TCSADRAIN, settings)
    return key

def saveTerminalSettings():
    if sys.platform == 'win32':
        return None
    return termios.tcgetattr(sys.stdin)

def restoreTerminalSettings(old_settings):
    if sys.platform == 'win32':
        return
    termios.tcsetattr(sys.stdin, termios.TCSADRAIN, old_settings)

def vels(speed, turn):
    return "currently:\tspeed: %s\tturn: %s\tmotion_mode: %s " % (speed,turn,motion_mode)

if __name__=="__main__":
    settings = saveTerminalSettings()

    rospy.init_node("tianrover_teleop_keybroad")

    speed = rospy.get_param("~speed", 0.2)
    turn  = rospy.get_param("~turn",0.0)
    motion_mode = rospy.get_param("~motion_mode", 'ackermann')
    speed_limit = rospy.get_param("~speed_limit", 1000)
    turn_limit = rospy.get_param("~turn_limit", 1000)
    repeat = rospy.get_param("~repeat_rate", 0.0)
    key_timeout = rospy.get_param("~key_timeout", 0.5)
    stamped = rospy.get_param("~stamped", False)
    cmd_frame = rospy.get_param("~frame_id", '')
    
    # Set up the publisher for the ackermann_msgs message
    if stamped:
        ackerman_msg = AckermannDriveStamped
        motion_mode_msg = String

    pub_thread = PublishThread(repeat)

    steering_angle_velocity = 0
    acceleration= 0
    jerk = 0
    status = 0
    old_motion_mode = ''

    try:
        pub_thread.wait_for_subscribers()
        pub_thread.update(speed, turn, motion_mode)

        print(msg)
        print(vels(speed, turn))

        while(1):
            key = getKey(settings, key_timeout)
            
            # motion_mode
            if key != '' and key == 'a' or key == 's' or key == 'z':
                motion_mode = motion_mode_switch(key)
                old_motion_mode = motion_mode
            else:
                motion_mode = ''
                # print("motion_mode set error!")
            
            if key in moveBindings.keys():
                speed = moveBindings[key][0]
                turn = moveBindings[key][1]
            elif key in speedBindings.keys():
                speed = min(speed_limit, speed * speedBindings[key][0])
                turn = min(turn_limit, turn * speedBindings[key][1])
                if speed == speed_limit:
                    print("Linear speed limit reached!")
                if turn == turn_limit:
                    print("Angular speed limit reached!")
                print(vels(speed, turn))
                if (status == 14):
                    print(msg)
                status = (status +1) % 15
            else:
                # Skip update cmd if key timeout and robot already stopped
                if key == '' and speed == 0 and turn == 0:
                    continue
                speed = 0
                turn = 0
                if(key == '\x03'):       # Ctrl + c
                    break
            
            # avoid the except key('a','s','z') to change the current motion_mode
            if key != 'a' or key != 's' or key !='z':
                motion_mode = old_motion_mode
            pub_thread.update(speed, turn, motion_mode)

    except Exception as e:
        #print(f"Exception in thread: {e}")
        print(e)
        raise

    finally:
        pub_thread.stop()
        restoreTerminalSettings(settings)
