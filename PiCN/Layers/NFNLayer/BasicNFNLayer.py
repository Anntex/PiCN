"""Basic NFN Layer Implementation"""
import multiprocessing

from typing import Dict

from PiCN.Packets import Interest, Content, Nack
from PiCN.Processes import LayerProcess
from PiCN.Layers.NFNLayer.NFNComputationTable import BaseNFNComputationTable
from PiCN.Layers.NFNLayer.NFNComputationTable import NFNComputationList
from PiCN.Layers.NFNLayer.NFNComputationTable import NFNComputationState
from PiCN.Layers.NFNLayer.NFNExecutor import BaseNFNExecutor
from PiCN.Layers.NFNLayer.Parser import DefaultNFNParser
from PiCN.Layers.NFNLayer.NFNOptimizer import BaseNFNOptimizer
from PiCN.Layers.NFNLayer.NFNOptimizer import ToDataFirstOptimizer
from PiCN.Layers.NFNLayer.R2C import TimeoutR2CClient

class BasicNFNLayer(LayerProcess):
    """Basic NFN Layer Implementation"""

    def __init__(self, icn_data_structs: Dict, executors: Dict[str, type(BaseNFNExecutor)],
                 computationTable: BaseNFNComputationTable=None, log_level: int=255):
        super().__init__("NFN-Layer", log_level=log_level)
        self.icn_data_structs = icn_data_structs
        self.executors = executors
        self.r2cclient = TimeoutR2CClient()
        self.computation_table: BaseNFNComputationTable = NFNComputationList(self.r2cclient) \
            if computationTable == None else computationTable
        self.parser: DefaultNFNParser = DefaultNFNParser()
        self.optimizer: BaseNFNOptimizer = ToDataFirstOptimizer(self.icn_data_structs)

    def data_from_lower(self, to_lower: multiprocessing.Queue, to_higher: multiprocessing.Queue, data):
        """handle incomming data from the lower layer """
        if isinstance(data, Interest):
            self.handleInterest(data)
        elif isinstance(data, Content):
            self.handleContent(data)
        elif isinstance(data, Nack):
            self.handleNack(data)

    def data_from_higher(self, to_lower: multiprocessing.Queue, to_higher: multiprocessing.Queue, data):
        """Currently no higher layer than the NFN Layer"""
        pass

    def handleInterest(self, interest: Interest):
        """start a new computation from an interest or send it down if no NFN tag"""
        #TODO R2C!!!
        if interest.name.components[-1] != b"NFN": #send non NFN interests back
            self.queue_to_lower.put(interest)
            return
        #parse interest and create computation
        nfn_str, prepended_name = self.parser.network_name_to_nfn_str(interest.name)
        ast = self.parser.parse(nfn_str)
        self.computation_table.add_computation(interest.name, interest, ast)

        #request required data
        required_optimizer_data = self.optimizer.required_data(ast)

        self.computation_table.update_status(interest.name, NFNComputationState.FWD)
        if required_optimizer_data != []: # Optimizer requires additional data
            raise NotImplemented("Global Optimizing not implemeted yet")
            #TODO add to await list, send messages to reqeust data
            return

        #if no data are required we can continue directly, otherwise data handler must call that
        self.forwarding_descision()

    def handleContent(self, content: Content):
        pass

    def handleNack(self, nack: Nack):
        pass

    def forwarding_descision(self):
        """Decide weather a computation should be executed locally or be forwarded"""

