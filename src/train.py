import glob
import logging.config
import os
from logging import getLogger
from typing import Any, Dict

import torch
import torch.nn as nn
import yaml

import unet
import utils
from datasets import SegmentationDataset
from trainer import SegmentationTrainer

with open('logger_conf.yaml', 'r') as f:
    log_config: Dict[str, Any] = yaml.safe_load(f.read())
    logging.config.dictConfig(log_config)

logger = getLogger(__name__)


def load_config(path: str) -> dict:
    with open(path, 'r') as f:
        return yaml.load(f, Loader=yaml.FullLoader)


def dump_config(path: str, dic: dict):
    with open(path, 'w') as f:
        yaml.dump(dic, f)


def load_text(path: str) -> list:
    with open(path, 'r', encoding='utf-8') as f:
        text = f.read().split('\n')
    return text


def load_dataset():
    X = glob.glob('../VOCdevkit/VOC2012/JPEGImages/*')
    y = glob.glob('../VOCdevkit/VOC2012/SegmentationClass/*')

    train_path = '../VOCdevkit/VOC2012/ImageSets/Segmentation/train.txt'
    valid_path = '../VOCdevkit/VOC2012/ImageSets/Segmentation/val.txt'

    train_images = load_text(train_path)
    valid_images = load_text(valid_path)

    X_train, X_valid = [], []
    for x in X:
        if os.path.splitext(os.path.basename(x))[0] in train_images:
            X_train.append(x)
        elif os.path.splitext(os.path.basename(x))[0] in valid_images:
            X_valid.append(x)

    y_train, y_valid = [], []
    for i in y:
        if os.path.splitext(os.path.basename(i))[0] in train_images:
            y_train.append(i)
        elif os.path.splitext(os.path.basename(i))[0] in valid_images:
            y_valid.append(i)

    return X_train[:5], X_valid[:5], y_train[:5], y_valid[:5]


if __name__ == '__main__':
    utils.seed_everything()

    cfg: Dict[str, Any] = load_config('./config.yml')
    logger.info(f'Training configurations: {cfg}')

    device: str = 'cuda' if torch.cuda.is_available() else 'cpu'

    model = unet.UNetResNet34(cfg['num_classes'])
    model = model.to(device)

    criterion = nn.CrossEntropyLoss()

    X_train, X_valid, y_train, y_valid = load_dataset()

    dtrain = SegmentationDataset(
        X=X_train, y=y_train, num_classes=cfg['num_classes'],
        img_size=cfg['img_size']
    )
    train_loader = torch.utils.data.DataLoader(dtrain,
                                               batch_size=cfg['batch_size'],
                                               shuffle=True,
                                               drop_last=True)

    dvalid = SegmentationDataset(
        X=X_valid, y=y_valid, num_classes=cfg['num_classes'],
        img_size=cfg['img_size']
    )
    valid_loader = torch.utils.data.DataLoader(
        dvalid,
        batch_size=cfg['batch_size']
    )

    optimizer = torch.optim.SGD(model.parameters(),
                                lr=cfg['max_lr'],
                                momentum=cfg['momentum'],
                                weight_decay=cfg['weight_decay'])

    scheduler = torch.optim.lr_scheduler.CosineAnnealingLR(
        optimizer,
        T_max=cfg['num_epochs'],
        eta_min=cfg['min_lr']
    )

    trainer = SegmentationTrainer(
        model, optimizer, criterion, cfg['num_classes']
    )
    best_loss = 10000.
    for epoch in range(1, 1 + cfg['num_epochs']):
        train_loss = trainer.epoch_train(train_loader)
        valid_loss = trainer.epoch_eval(valid_loader)
        if valid_loss < best_loss:
            best_loss = valid_loss
            path = os.path.join(
                '../weights', f'epoch{epoch}_loss{valid_loss:.3f}.pth'
            )
            torch.save(trainer.weights, path)

        scheduler.step()

        logger.info(f'EPOCH: [{epoch}/{cfg["num_epochs"]}]')
        logger.info(
            f'TRAIN LOSS: {train_loss:.3f}, VALID LOSS: {valid_loss:.3f}'
        )

    path = os.path.join('../configs', f'{best_loss}.yml')
    dump_config(path, cfg)
