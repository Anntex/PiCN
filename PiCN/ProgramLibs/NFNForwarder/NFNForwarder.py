"""NFN Forwarder for PICN"""

import multiprocessing
import time

from PiCN.Layers.NFNLayer import BasicNFNLayer
from PiCN.Layers.ChunkLayer import BasicChunkLayer
from PiCN.Layers.ICNLayer import BasicICNLayer
from PiCN.Layers.PacketEncodingLayer import BasicPacketEncodingLayer
from PiCN.Layers.LinkLayer import UDP4LinkLayer

from PiCN.Layers.ChunkLayer.Chunkifyer import SimpleContentChunkifyer
from PiCN.Layers.ICNLayer.ForwardingInformationBase import ForwardingInformationBaseMemoryPrefix
from PiCN.Layers.ICNLayer.PendingInterestTable import PendingInterstTableMemoryExact
from PiCN.Layers.NFNLayer.NFNEvaluator.NFNExecutor import NFNPythonExecutor
from PiCN.Layers.ICNLayer.ContentStore import ContentStoreMemoryExact
from PiCN.Layers.PacketEncodingLayer.Encoder import BasicEncoder, SimpleStringEncoder
from PiCN.Logger import Logger
from PiCN.Mgmt import Mgmt
from PiCN.Routing import BasicRouting

class NFNForwarder(object):
    """NFN Forwarder for PICN"""
#TODO add chunking layer
    def __init__(self, port=9000, log_level=255, encoder: BasicEncoder=None):
        # debug level
        logger = Logger("NFNForwarder", log_level)
        logger.info("Start PiCN NFN Forwarder on port " + str(port))

        # packet encoder
        if encoder == None:
            self.encoder = SimpleStringEncoder(log_level=log_level)
        else:
            encoder.set_log_level(log_level)
            self.encoder = encoder

        # initialize layers
        self.linklayer = UDP4LinkLayer(port, log_level=log_level)
        self.packetencodinglayer = BasicPacketEncodingLayer(self.encoder, log_level=log_level)
        self.icnlayer = BasicICNLayer(log_level=log_level)

        # setup data structures
        manager = multiprocessing.Manager()
        self.cs = ContentStoreMemoryExact(manager)
        self.fib = ForwardingInformationBaseMemoryPrefix(manager)
        self.pit = PendingInterstTableMemoryExact(manager)

        self.icnlayer.cs = self.cs
        self.icnlayer.fib = self.fib
        self.icnlayer.pit = self.pit

        self.chunkifier = SimpleContentChunkifyer()

        # setup chunklayer
        self.chunklayer = BasicChunkLayer(self.chunkifier, log_level=log_level)

        # setup nfn
        self.icnlayer._interest_to_app = True
        self.executors = {"PYTHON": NFNPythonExecutor}
        self.nfnlayer = BasicNFNLayer(self.icnlayer.manager, self.cs, self.fib, self.pit, self.executors,
                                      log_level=log_level)

        # setup communication queues
        self.q_link_packet_up = multiprocessing.Queue()
        self.q_packet_link_down = multiprocessing.Queue()

        self.q_packet_icn_up = multiprocessing.Queue()
        self.q_icn_packet_down = multiprocessing.Queue()

        self.q_routing_icn_up = multiprocessing.Queue()
        self.q_icn_routing_down = multiprocessing.Queue()

        self.q_icn_to_chunk = multiprocessing.Queue()
        self.q_chunk_to_icn = multiprocessing.Queue()

        self.q_chunk_to_nfn = multiprocessing.Queue()
        self.q_nfn_to_chunk = multiprocessing.Queue()

        # set link layer queues
        self.linklayer.queue_to_higher = self.q_link_packet_up
        self.linklayer.queue_from_higher = self.q_packet_link_down

        # set packet encoding layer queues
        self.packetencodinglayer.queue_to_lower = self.q_packet_link_down
        self.packetencodinglayer.queue_from_lower = self.q_link_packet_up
        self.packetencodinglayer.queue_to_higher = self.q_packet_icn_up
        self.packetencodinglayer.queue_from_higher = self.q_icn_packet_down

        # set icn layer queues
        self.icnlayer.queue_to_lower = self.q_icn_packet_down
        self.icnlayer.queue_from_lower = self.q_packet_icn_up
        self.icnlayer.queue_to_higher = self.q_icn_to_chunk
        self.icnlayer.queue_from_higher = self.q_chunk_to_icn

        #set chunklayer queues
        self.chunklayer.queue_to_lower = self.q_chunk_to_icn
        self.chunklayer.queue_from_lower = self.q_icn_to_chunk
        self.chunklayer.queue_to_higher = self.q_chunk_to_nfn
        self.chunklayer.queue_from_higher = self.q_nfn_to_chunk

        # set nfn layer
        self.nfnlayer.queue_to_lower = self.q_nfn_to_chunk
        self.nfnlayer.queue_from_lower = self.q_chunk_to_nfn

        # routing
        self.routing = BasicRouting(self.icnlayer.pit, None, log_level=log_level)  # TODO NOT IMPLEMENTED YET

        # mgmt
        self.mgmt = Mgmt(self.cs, self.fib, self.pit, self.linklayer, self.linklayer.get_port(), self.stop_forwarder,
                         log_level=log_level)

    def start_forwarder(self):
        # start processes
        self.linklayer.start_process()
        self.packetencodinglayer.start_process()
        self.icnlayer.start_process()
        self.icnlayer.ageing()
        self.chunklayer.start_process()
        self.nfnlayer.start_process()
        self.mgmt.start_process()

    def stop_forwarder(self):
        # Stop processes
        self.mgmt.stop_process()
        self.linklayer.stop_process()
        self.packetencodinglayer.stop_process()
        self.icnlayer.stop_process()
        self.nfnlayer.stop_process()

        # close queues file descriptors
        self.q_link_packet_up.close()
        self.q_packet_link_down.close()
        self.q_packet_icn_up.close()
        self.q_icn_packet_down.close()
        self.q_icn_to_chunk.close()
        self.q_chunk_to_icn.close()
        self.q_chunk_to_nfn.close()
        self.q_nfn_to_chunk.close()
