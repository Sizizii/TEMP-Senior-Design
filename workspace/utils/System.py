import pdb
import numpy as np
import torch
import torch.nn as nn
from datetime import datetime
from tqdm import trange
from typing import List
from models.Forecaster import Forecaster
from models.Classifier import Classifier
from common.config import *
from common.funcs import *
from utils.Prediction import Prediction


class System(object):
    def __init__(self, args):
        super().__init__()

        self.args = args

        print("==> Building forecaster...")
        lstm_config = {
            'input_size': len(names_for_input_features),
            'hidden_size': args.lstm_hidden_size,
            'num_layers': args.lstm_num_layers,
            'dropout': args.lstm_dropout,
            'batch_first': True,
        }
        mlp_config = {
            'num_layers': args.mlp_num_layers,
            'input_size': args.lstm_hidden_size,
            'hidden_size': args.mlp_hidden_size,
            'output_size': len(names_for_output_features),
            'dropout': args.mlp_dropout,
        }
        self.forecaster = Forecaster(lstm_config, mlp_config).to(device)
        self.forecaster.load_state_dict(torch.load(args.forecaster_save_path))
        self.forecaster.eval()

        """forecaster in & out:
        y = forecaster(x)
        x: torch.Tensor([batch size, sequence length, input size])
        y: torch.Tensor([batch size, sequence length, output size])
        """

        print("==> Building classifier...")
        self.classifier = Classifier()
        self.classifier.load_from_pkl(args.classifier_save_path)
    
        """classifier in & out:
        y = classifier.predict(X)
        X: np.array([..., input size])
        y: List[str]
        """
        
        self.month = datetime.now().month

    def predict_single_step(self, historical_data: torch.Tensor) -> Prediction:
        """get the next time step data based on historical data

        Args:
            historical_data (torch.Tensor): a Tensor with shape (historical length, input size) 
        """
        assert isinstance(historical_data, torch.Tensor)
        historical_data = torch.where(torch.isnan(historical_data), torch.full_like(historical_data, 0), historical_data)
        assert historical_data.shape == (self.args.historical_length, len(names_for_input_features))
        
        historical_data = normalize(historical_data.unsqueeze(0)).to(device)
        with torch.no_grad():
            pred = self.forecaster(historical_data)   
        next_step_data = pred.squeeze()[-1].cpu()      
        classifier_input = torch.cat((next_step_data, torch.tensor(self.month).unsqueeze(0))).unsqueeze(0).numpy()
        next_step_description = self.classifier.predict(classifier_input)[0]
        return Prediction(next_step_data, next_step_description)
    
    def predict_multi_step(self, historical_data: torch.Tensor, num_steps: int) -> List[Prediction]:
        """get a series of future data based on historical data

        Args:
            historical_data (torch.Tensor): a Tensor with shape (historical length, input size) 
            num_steps (int): number of future time steps to predict
        """
        ret = []
        input_data = historical_data
        for _ in range(num_steps):
            pred = self.predict_single_step(input_data)
            new_line = torch.cat((pred.TTPHW, torch.tensor(self.month).unsqueeze(0))).unsqueeze(0)
            input_data = torch.cat((input_data[1:], new_line), dim=0)
            ret.append(pred)
        
        return ret
